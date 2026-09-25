"""'이름을 부르다' v3 렌더러 (PRD v3, 2026-09-24).

v2(`build_episode.py`)는 1~20화를 다시 뽑을 수 있게 그대로 둔다. v3에서 바뀐 것:

- **흑백 사진.** 세피아 대신 중성 흑백 + 그레인 + 비네팅 (§16, 2026-09-24 사용자 지시)
- **고딕 자막, 가운데 정렬, 한 장 최대 2줄**, `*단어*`는 DEEP RED (§15, §18)
- 브랜드 컷 없음. 이름은 **06 한 번만** — 암전 → "오늘 우리가 다시 부를 이름." → 초상 → 이름 (§10)
- 07 엔딩 카드 — 먹색 바탕, "오늘, 이 이름 하나만 기억해주세요." / 이름을 부르다 (§11)
- 05(RESULT)부터 카메라를 느리게, BGM을 낮춘다 (§9, §19)
- 프레임을 PNG로 쌓지 않고 ffmpeg에 바로 흘려보낸다 — v2는 편당 2GB가 쌓였다(PRD_v2 §14)

사용: python3 scripts/build_episode_v3.py drafts/script_v3_01_chu.json
"""
import json
import math
import os
import random
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archive_layout import H, NANUM_XBOLD, NOTO_SERIF, W, load, make_paper  # noqa: E402
from build_episode import SEG_TARGET_DB, mean_db, voiced_end, wav_dur  # noqa: E402

# 문장 사이 무음 상한 / 문장 끝 여운 (초). v2는 0.28 / 0.15였다.
# 2026-09-25 사용자 지시 "문장과 문장 사이 무음을 조금 줄여" → 0.18 / 0.08. 대본 JSON의
# gap_max·tail_keep으로 회차별 조정 가능.
GAP_MAX = 0.18
TAIL_KEEP = 0.08
import make_bgm  # noqa: E402

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FONT_DIR = os.path.join(BASE, "assets/fonts")
NOTO_SANS = os.path.join(FONT_DIR, "NotoSansKR-var.ttf")
EULJIRO = os.path.join(FONT_DIR, "BMEULJIRO.ttf")     # 배민 을지로체 — 타이틀·강조 (2026-09-25 사용자 지시)
HANNA = os.path.join(FONT_DIR, "BMHANNA.ttf")         # 배민 한나체 Pro — 자막 본문 (2026-09-25 사용자 지시)
SHOT_SEC = 3.0                                        # 컷 전환 간격 목표. 4.5초 → 3초 (1.5배 빠르게, 사용자 지시)
LOCK = os.path.join(BASE, "output/audio/locked_takes")
FPS = 30

# ── 색 (PRD §14) ── 검정 바탕 위 글자라 RED는 토큰보다 한 단계 밝게 쓴다. #9B1C1C는 먹색 위에서 안 읽힌다.
BLACK = (14, 13, 11)
IVORY = (237, 230, 214)
SEPIA = (160, 139, 106)
DIM = (120, 112, 100)
RED = (196, 42, 42)

# ── 배치 ── 세이프 영역: 상단 250 / 하단 430 / 우측 170 (PRD_v2 실측)
# 상단 타이틀 — 썰쇼츠(`ssul/pipeline/layout.py`)와 같은 규격 (2026-09-24 사용자 지시).
# 최대 120px · 좌우 여백 80px · 폭에 맞춰 자동 축소 · 두 줄은 display_title에 "\n"으로 나눈다.
# 밴드도 썰쇼츠와 같이 화면 12.7%(244)에서 시작한다. 연도 스탬프는 뺐다(같은 지시).
TITLE_Y = 244
TITLE_MAX, TITLE_PAD = 176, 60      # 2026-09-25 1.3배 확대 (136→176), 여백 80→60
TITLE_LINE = 1.12                    # 줄 간격 (글자 크기 배수)
PHOTO_TOP, PHOTO_H = 540, 720        # 타이틀이 커진 만큼 내리고 3:2로 줄였다
CAP_TOP = 1330                       # 자막은 한 줄씩 뜬다 — 사진 아래 가운데
CAP_SIZE, CAP_WEIGHT = 62, 600
CAP_LINE = int(CAP_SIZE * 1.45)
CAP_MAX_W = W - 170 * 2              # 가운데 정렬이라 좌우 모두 우측 안전선만큼 비운다
TYPE_RATIO = 0.92                    # 자막 장 넘김을 발화 길이의 92% 안에 끝낸다
XFADE = 9                            # 컷 전환 크로스페이드 프레임

BLACKOUT = 0.4                       # 이름 공개 직전 암전 (§10: 0.3~0.5)
REVEAL_PRE = 0.35                    # 초상이 먼저 뜨고 나서 말이 시작되는 사이
NAME_HOLD = 1.0                      # 이름 뒤 여운 (PRD_v2: 1.25배속 기준 1.0)
ENDING_HOLD = 1.6
FINAL_HOLD = 2.0                     # 07 엔딩이 없을 때 이름 뒤 여운 (BGM 잔향으로 닫는다)


# ───────────────────────── 사진 ─────────────────────────

def _grain_tiles(w, h, n=4, seed=3):
    rnd = np.random.default_rng(seed)
    return [Image.fromarray(rnd.normal(128, 22, (h // 2, w // 2)).clip(0, 255).astype(np.uint8))
            .resize((w, h), Image.BILINEAR) for _ in range(n)]


def _vignette(w, h, strength=0.55):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).ellipse([-w * .15, -h * .2, w * 1.15, h * 1.2], fill=255)
    return m.filter(ImageFilter.GaussianBlur(min(w, h) * 0.2)), strength


def grade_color(img, mode=None):
    """사진 톤. `COLOR_MODE`(대본 `"color": true/false`)로 컬러/흑백을 고른다.

    - 컬러(2026-09-25 사용자 지시, 사명대사 편부터): 채도만 살짝 누른 필름 톤. 세피아로 물들이지 않는다.
    - 흑백(김용환 편까지): 중성 흑백, 암부는 배경 먹색에 맞춘다.
    """
    mode = COLOR_MODE if mode is None else mode
    if mode:
        img = ImageEnhance.Color(img).enhance(0.86)
        img = ImageEnhance.Contrast(img).enhance(1.06)
        r, g, b = img.split()
        r = r.point(lambda v: min(255, int(v * 1.03)))
        b = b.point(lambda v: int(v * 0.95))
        return Image.merge("RGB", (r, g, b))
    g = ImageEnhance.Contrast(img.convert("L")).enhance(1.10)
    g = g.point(lambda p: int(BLACK[0] + (p / 255) ** 1.12 * (232 - BLACK[0])))
    return Image.merge("RGB", (g, g, g))


COLOR_MODE = False


def _feather(w, h, top=70, bottom=150):
    """사진 위아래를 먹색으로 녹인다 — 카드가 아니라 화면에 배어 있는 느낌."""
    a = np.ones((h, w), np.float32)
    ramp_t = np.linspace(0, 1, top) ** 1.4
    ramp_b = np.linspace(1, 0, bottom) ** 1.4
    a[:top] *= ramp_t[:, None]
    a[h - bottom:] *= ramp_b[:, None]
    return Image.fromarray((a * 255).astype(np.uint8))


class Shot:
    """한 컷의 사진. 원본을 한 번 그레이딩해 두고 프레임마다 창만 잘라낸다."""

    def __init__(self, path, seed, pace="normal", box=None):
        src = Image.open(path).convert("RGB")
        box = box or (W, PHOTO_H)
        self.box = box
        bw, bh = box
        # 박스를 덮는 크기의 1.3배까지만 들고 있는다 (프레임마다 리사이즈 비용을 줄인다)
        s = max(bw / src.width, bh / src.height) * 1.3
        self.src = grade_color(src.resize((int(src.width * s), int(src.height * s)), Image.LANCZOS))
        rnd = random.Random(seed)
        self.zoom_in = rnd.random() < 0.6
        self.dir = rnd.choice([(1, 0), (-1, 0), (0.6, 0.4), (-0.6, 0.4), (0.5, -0.4)])
        self.pace = pace
        self.vig, self.vig_k = _vignette(bw, bh)
        self.feather = _feather(bw, bh)
        self.grain = _grain_tiles(bw, bh)

    def view(self, t, fi):
        sw, sh = self.src.size
        bw, bh = self.box
        ar = bw / bh
        base_w, base_h = (sh * ar, sh) if sw / sh > ar else (sw, sw / ar)
        if self.pace == "hook":                   # 훅 — 빠른 줌인 후 천천히 (§5 HOOK)
            k = 1 - (1 - min(1.0, t / 0.35)) ** 3
            z = 0.20 * k + 0.04 * t
            zoom_in = True
        elif self.pace == "slow":                 # RESULT — 움직임 최소 (§9)
            z, zoom_in = 0.035 * t, self.zoom_in
        else:
            z, zoom_in = 0.09 * t, self.zoom_in
        sc = (1 - z) if zoom_in else (1 - 0.09 + z)
        cw, ch = base_w * sc, base_h * sc
        drift = 0.02 if self.pace == "slow" else 0.045
        dx, dy = self.dir
        cx = sw / 2 + dx * min((sw - cw) / 2, sw * drift) * (t * 2 - 1)
        cy = sh / 2 + dy * min((sh - ch) / 2, sh * drift) * (t * 2 - 1)
        x0 = max(0, min(sw - cw, cx - cw / 2))
        y0 = max(0, min(sh - ch, cy - ch / 2))
        v = self.src.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize(self.box, Image.BILINEAR)
        v = Image.composite(v, ImageEnhance.Brightness(v).enhance(1 - self.vig_k), self.vig)
        return Image.blend(v, Image.merge("RGB", (self.grain[fi % len(self.grain)],) * 3), 0.06)


# ───────────────────────── 자막 ─────────────────────────

def parse_marks(text):
    """`*단어*` → (별표 뺀 글자열, 강조 여부 리스트)."""
    out, flags, on = [], [], False
    for ch in text:
        if ch == "*":
            on = not on
            continue
        out.append(ch)
        flags.append(on)
    return "".join(out), flags


def wrap_marked(text, flags, font, max_w):
    """어절 단위 줄바꿈. 구두점으로 끝난 어절 뒤, 줄이 절반 넘게 찼으면 거기서 끊는다."""
    d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    words, i = [], 0
    for w in text.split(" "):
        words.append((w, flags[i:i + len(w)]))
        i += len(w) + 1
    lines, cur, curf = [], "", []
    for w, f in words:
        trial = f"{cur} {w}" if cur else w
        if cur and d.textlength(trial, font=font) > max_w:
            lines.append((cur, curf))
            cur, curf = w, list(f)
            continue
        curf = curf + ([False] if cur else []) + list(f)
        cur = trial
        if w[-1:] in ",." and d.textlength(cur, font=font) > max_w * 0.5:
            lines.append((cur, curf))
            cur, curf = "", []
    if cur:
        lines.append((cur, curf))
    return lines


def _chunks(text, flags, font, max_w):
    """자막을 **한 줄씩** 띄울 조각으로 나눈다 (2026-09-24 사용자 지시).

    1) 쉼표·마침표에서 먼저 끊는다 — 말의 호흡과 자막 단위를 맞춘다
    2) 그래도 한 줄에 안 들어가면 어절 사이 중 **좌우 폭이 가장 비슷한 곳**에서 나눈다.
       앞에서부터 채우면 "쫓기던 김구를 숨겨 준 중국인이 / 있었습니다."처럼 꼬리가 남는다
    3) 강조(`*…*`) 구간 안의 띄어쓰기에서는 끊지 않는다 — "광둥 / 사람"으로 갈리면 강조가 깨진다
    """
    d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    width = lambda ws: d.textlength(" ".join(w for w, _ in ws), font=font)

    # 어절 단위로 자르되, 강조 구간 안의 공백은 어절을 잇는다
    words, cur, curf = [], "", []
    for i, ch in enumerate(text):
        if ch == " " and not (flags[i - 1] and i + 1 < len(flags) and flags[i + 1]):
            words.append((cur, curf))
            cur, curf = "", []
        else:
            cur += ch
            curf.append(flags[i])
    if cur:
        words.append((cur, curf))

    # 대본의 " / "는 사람이 정한 줄바꿈이다 — 자동 분할보다 우선한다
    clauses, acc = [], []
    for w in words:
        if w[0] == "/":
            if acc:
                clauses.append(acc)
            acc = []
            continue
        acc.append(w)
        if w[0][-1:] in ",.?!":
            clauses.append(acc)
            acc = []
    if acc:
        clauses.append(acc)

    def split(ws):
        if len(ws) == 1 or width(ws) <= max_w:
            return [ws]
        best = min(range(1, len(ws)), key=lambda k: max(width(ws[:k]), width(ws[k:])))
        return split(ws[:best]) + split(ws[best:])

    out = []
    for c in clauses:
        for ws in split(c):
            line = " ".join(w for w, _ in ws)
            fl = []
            for j, (w, f) in enumerate(ws):
                fl += ([False] if j else []) + list(f)
            out.append((line, fl))
    return out


def caption_pages(raw):
    font = load(HANNA, CAP_SIZE)
    text, flags = parse_marks(raw)
    return [[ln] for ln in _chunks(text, flags, font, CAP_MAX_W)], font


def _em_font(font):
    """강조 서체 — 같은 크기의 을지로체. 베이스라인을 맞춰 그리므로 크기를 달리하지 않는다."""
    key = ("em", font.size)
    if key not in _TITLE_CACHE:
        _TITLE_CACHE[key] = load(EULJIRO, font.size)
    return _TITLE_CACHE[key]


def draw_lines(fr, lines, font, top, fill=IVORY, alpha=1.0):
    """한 줄을 그린다. `*단어*` 구간은 **을지로체 + 붉은색** (2026-09-25 사용자 지시)."""
    d = ImageDraw.Draw(fr)
    em = _em_font(font) if font.path != EULJIRO else font
    y = top
    for text, flags in lines:
        flags = flags + [False] * (len(text) - len(flags))
        runs, run, run_red = [], "", None
        for ch, red in zip(text, flags):
            if run_red is not None and red != run_red:
                runs.append((run, run_red))
                run = ""
            run += ch
            run_red = red
        if run:
            runs.append((run, run_red))
        total = sum(d.textlength(r, font=em if red else font) for r, red in runs)
        x = (W - total) / 2
        # 서체가 달라도 글자 밑선(baseline)을 한 줄에 맞춘다 — 을지로체만 위로 뜨던 문제
        base = y + font.getmetrics()[0]
        for r, red in runs:
            f = em if red else font
            d.text((x, base), r, font=f, fill=RED if red else fill, anchor="ls")
            x += d.textlength(r, font=f)
        y += CAP_LINE


def draw_centered(fr, text, font, y, fill):
    d = ImageDraw.Draw(fr)
    d.text(((W - d.textlength(text, font=font)) / 2, y), text, font=font, fill=fill)


def with_alpha(base, layer_fn, a):
    if a >= 0.999:
        layer_fn(base)
        return base
    if a <= 0.001:
        return base
    top = base.copy()
    layer_fn(top)
    return Image.blend(base, top, a)


# ───────────────────────── 오디오 ─────────────────────────

def ff(args):
    subprocess.run(["ffmpeg", "-y", *args], check=True, capture_output=True)


def silence(sec, dst):
    ff(["-f", "lavfi", "-t", f"{sec:.3f}", "-i", "anullsrc=r=44100:cl=mono", dst])
    return dst


def norm(src, dst, speed=None):
    af = f"volume={SEG_TARGET_DB - mean_db(src):+.2f}dB"
    if speed:
        af = f"atempo={speed}," + af + (f",silenceremove=stop_periods=-1:stop_duration={GAP_MAX}"
                                        f":stop_threshold=-45dB" if GAP_MAX else "")
    ff(["-i", src, "-filter:a", af, "-ar", "44100", "-ac", "1", dst])
    if speed and TAIL_KEEP is not None:
        ve = voiced_end(dst)
        if wav_dur(dst) - ve > TAIL_KEEP + 0.02:
            cut = dst + ".t.wav"
            ff(["-i", dst, "-t", f"{ve + TAIL_KEEP:.3f}", "-ar", "44100", "-ac", "1", cut])
            os.replace(cut, dst)
    return dst


def build_audio(script, audio_dir, tmp):
    """세그먼트별 오디오 조각과 타임라인을 만든다. 06·07은 공용 음성 + 이름으로 조립."""
    global GAP_MAX, TAIL_KEEP
    GAP_MAX = float(script.get("gap_max", GAP_MAX))
    TAIL_KEEP = float(script.get("tail_keep", TAIL_KEEP))
    speed = float(script.get("playback_speed", 1.25))
    name_wav = os.path.join(BASE, script.get("name_audio", ""))   # 이름 낭독은 2026-09-25부터 없다
    parts, timeline, t = [], [], 0.0
    has_ending = any(x.get("kind") == "ending" for x in script["segments"])
    for seg in script["segments"]:
        sid, kind = seg["id"], seg.get("kind", "body")
        if kind == "reveal":
            # 2026-09-25 사용자 확정 — "오늘 부를 이름, ○○○. 이런 사람이 있어서 지금의 대한민국이 있습니다."
            # 호명 문구·마무리 문장은 공용 음성, 이름은 캐리어 문장에서 잘라낸 회차 음성(name_audio).
            pieces = [("pre", silence(REVEAL_PRE, os.path.join(tmp, "pre.wav")))]
            if script.get("name_audio"):
                pieces += [("call", norm(os.path.join(LOCK, "common_v3_call.wav"), os.path.join(tmp, "call.wav"))),
                           ("gap1", silence(0.45, os.path.join(tmp, "gap1.wav"))),
                           ("name", norm(name_wav, os.path.join(tmp, "name.wav"))),
                           ("gap2", silence(0.6, os.path.join(tmp, "gap2.wav")))]
            pieces += [("remember", norm(os.path.join(LOCK, script.get("reveal_audio", "common_C_tail.wav")),
                                         os.path.join(tmp, "remember.wav"))),
                       ("hold", silence(FINAL_HOLD, os.path.join(tmp, "hold.wav")))]
        elif kind == "ending":
            pieces = [("remember", norm(os.path.join(LOCK, "common_v3_remember.wav"),
                                        os.path.join(tmp, "remember.wav"))),
                      ("hold", silence(ENDING_HOLD, os.path.join(tmp, "ehold.wav")))]
        else:
            # generate_tts.py(2026-09-25)는 자막 한 줄(" / ")마다 `{id}_L{k}.wav`로 따로 뽑는다.
            # 줄 음성이 있으면 그 경계를 자막 넘김 시점으로 쓴다 — 글자 수 비율보다 정확하다.
            import glob
            line_files = sorted(glob.glob(os.path.join(audio_dir, f"{sid}_L*.wav")),
                                key=lambda p: int(p.rsplit("_L", 1)[1][:-4]))
            # ⚠️ 통짜 문장 음성이 있으면 그것을 우선한다. 줄 단위 음성은 나레이션이 끊겨 폐기됐다(2026-09-25)
            if os.path.exists(os.path.join(audio_dir, f"{sid}.wav")):
                line_files = []
            if line_files:
                pieces = [(f"L{k}", norm(lf, os.path.join(tmp, f"{sid}_L{k}.wav"), speed=speed))
                          for k, lf in enumerate(line_files)]
            else:
                src = os.path.join(audio_dir, f"{sid}.wav")
                if not os.path.exists(src):
                    raise SystemExit(f"❌ 음성 없음: {src}\n   generate_tts.py로 먼저 뽑으세요.")
                pieces = [("voice", norm(src, os.path.join(tmp, f"{sid}.wav"), speed=speed))]
        sub, st = {}, t
        for tag, p in pieces:
            d = wav_dur(p)
            sub[tag] = (t, t + d)
            parts.append(p)
            t += d
        timeline.append({"seg": seg, "start": st, "end": t, "sub": sub})

    lst = os.path.join(tmp, "concat.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.abspath(p)}'\n" for p in parts)
    out = os.path.join(audio_dir, "narration_v3.wav")
    ff(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out])
    return out, timeline, t


def build_bgm(dst, total, timeline, script=None):
    script = script or {}
    """make_bgm의 드론·단음·스팅 위에 v3 볼륨 곡선을 씌운다 (PRD §19).

    초반 1.0 → RESULT부터 0.55로 내려감 → 암전에서 0 (순간 정적) → 문구 0.5
    → 이름에서 스팅이 올라옴 → 엔딩은 잔향으로 빠진다.
    """
    rev = next(x for x in timeline if x["seg"].get("kind") == "reveal")
    name_at = rev["sub"]["remember"][0]
    if script.get("bgm") == "anthem":                       # 애국가풍 (2026-09-25)
        import make_bgm_anthem
        make_bgm_anthem.build(total, rev["start"], dst)
    else:
        make_bgm.build(total, rev["start"], dst)
    with wave.open(dst) as w:
        sr = w.getframerate()
        d = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    res = next((x["start"] for x in timeline if x["seg"]["id"].startswith("05")), rev["start"])
    tt = np.arange(len(d)) / sr
    env = np.interp(tt, [0, res, res + 1.5, rev["start"] - 0.3, rev["start"] + 0.6, total],
                        [1.0, 1.0, 0.55, 0.55, 1.1, 0.7])
    fade = np.clip((total - tt) / 1.2, 0, 1)
    d = np.clip(d * env * fade, -32768, 32767).astype(np.int16)
    with wave.open(dst, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(d.tobytes())
    return name_at


# ───────────────────────── 화면 ─────────────────────────

def body_frame(paper, shot, seg, pages, font, t, fi, lt, title, ai, caption=True):
    fr = paper.copy()
    v = shot.view(t, fi)
    fr.paste(v, (0, PHOTO_TOP), shot.feather)
    d = ImageDraw.Draw(fr)
    draw_title(fr, title)
    if ai:                                           # §16 — AI 재현 이미지는 실제 사진과 구분한다
        fa = load(NOTO_SANS, 22, weight=400)
        d.text((W - 170 - d.textlength("AI 재현 이미지", font=fa), PHOTO_TOP + PHOTO_H - 190),
               "AI 재현 이미지", font=fa, fill=DIM)
    if not caption:
        return fr
    return draw_caption_at(fr, pages, font, lt)


def draw_caption_at(fr, pages, font, lt, bounds=None):
    """진행도 lt에 맞는 자막 장을 그린다. 전환 페이드와 분리해 자막끼리 겹치지 않게 한다.

    bounds = 줄 음성의 시작 지점 목록(세그먼트 안 진행비율). 있으면 그 시점에 장을 넘긴다.
    """
    if bounds and len(bounds) == len(pages):
        pi = max(i for i, b0 in enumerate(bounds) if lt >= b0 - 1e-6) if lt >= bounds[0] else 0
        a = 1.0
        if pi and lt - bounds[pi] < 0.05:
            a = max(0.0, (lt - bounds[pi]) / 0.05)
        return with_alpha(fr, lambda im: draw_lines(im, pages[pi], font, CAP_TOP), a)
    # 장 넘김: 글자 수에 비례해 발화 길이의 TYPE_RATIO 안에서 넘긴다
    counts = [sum(len(l[0]) for l in p) for p in pages]
    tot, acc, pi = sum(counts), 0, 0
    for k, c in enumerate(counts):
        if lt * TYPE_RATIO < (acc + c) / tot or k == len(counts) - 1:
            pi = k
            break
        acc += c
    a = 1.0
    page_start = acc / tot / TYPE_RATIO if pi else 0
    if pi and lt - page_start < 0.06:               # 다음 장은 살짝 떠오르며 바뀐다
        a = max(0.0, (lt - page_start) / 0.06)
    return with_alpha(fr, lambda im: draw_lines(im, pages[pi], font, CAP_TOP), a)


_TITLE_CACHE = {}


def title_font(title):
    """두 줄 중 긴 줄이 (W - 여백*2)에 들어가는 가장 큰 크기. 상한 TITLE_MAX. 을지로체."""
    if title not in _TITLE_CACHE:
        d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        plain = title.replace("*", "")
        size = TITLE_MAX
        while size > 40:
            f = load(EULJIRO, size)
            if max(d.textlength(l, font=f) for l in plain.split("\n")) <= W - TITLE_PAD * 2:
                break
            size -= 2
        _TITLE_CACHE[title] = (load(EULJIRO, size), size)
    return _TITLE_CACHE[title]


def draw_title(fr, title):
    """타이틀. `*단어*`는 붉게 (자막과 같은 표기)."""
    if not title:
        return
    f, size = title_font(title)
    for i, raw in enumerate(title.split("\n")):
        text, flags = parse_marks(raw)
        draw_lines(fr, [(text, flags)], f, TITLE_Y + i * size * TITLE_LINE, fill=IVORY)


class Portrait:
    def __init__(self, path, max_w=560, max_h=None):
        max_h = max_h or PHOTO_H - 40
        src = Image.open(path).convert("RGB")
        s = min(max_w / src.width, max_h / src.height)
        # 초상도 배경 컷과 같은 흑백 톤으로 (원본 png가 세피아라 그대로 두면 혼자 색이 뜬다)
        self.img = grade_color(src.resize((int(src.width * s), int(src.height * s)), Image.LANCZOS))
        self.grain = _grain_tiles(*self.img.size)
        if "blank_plate" in path:                  # 사진이 없는 회차 — 인화지 위에 표기 (2026-09-25 사용자 지시)
            d = ImageDraw.Draw(self.img)
            f = load(NOTO_SERIF, 40, weight=600)
            txt = "남아 있는 사진 없음"
            d.text(((self.img.width - d.textlength(txt, font=f)) / 2, self.img.height / 2 - 20),
                   txt, font=f, fill=(58, 54, 50))
        b = 10
        self.card = Image.new("RGB", (self.img.width + b * 2, self.img.height + b * 2), (205, 196, 178))
        self.b = b

    def paste(self, fr, y, fi, t, alpha=1.0):
        z = 1 + 0.025 * t                          # 초상은 거의 움직이지 않는다
        im = self.img.resize((int(self.img.width * z), int(self.img.height * z)), Image.BILINEAR)
        im = im.crop(((im.width - self.img.width) // 2, (im.height - self.img.height) // 2,
                      (im.width - self.img.width) // 2 + self.img.width,
                      (im.height - self.img.height) // 2 + self.img.height))
        im = Image.blend(im, Image.merge("RGB", (self.grain[fi % 4],) * 3), 0.05)
        card = self.card.copy()
        card.paste(im, (self.b, self.b))
        x = (W - card.width) // 2
        if alpha < 1:
            base = fr.crop((x, y, x + card.width, y + card.height))
            card = Image.blend(base, card, alpha)
        fr.paste(card, (x, y))
        return y + card.height


def reveal_frame(script, portrait, paper, title, tsec, sub, fi):
    """06 — 앞 컷과 같은 레이아웃에 초상이 바로 뜬다 (2026-09-25 사용자 지시).

    암전도, 문구가 떠올라 위로 비켜서는 연출도 없다. 사진 밴드 자리에 초상이 들어오고
    자막 자리에 이름표(이름 · 생몰 · 신분 · 출처)가 놓인다. 나레이션은 "기억하겠습니다."뿐이다.
    """
    fr = paper.copy()
    draw_title(fr, title)
    st = sub["pre"][0]
    t = (tsec - st) / max(0.1, sub["hold"][1] - st)
    y = PHOTO_TOP + (PHOTO_H - portrait.card.height) // 2
    bottom = portrait.paste(fr, y, fi, t)
    name, dates, role = (script["nameplate"] + ["", "", ""])[:3]
    d = ImageDraw.Draw(fr)
    fn = load(NANUM_XBOLD, 96)
    ny = max(bottom + 28, CAP_TOP - 10)
    d.text(((W - d.textlength(name, font=fn)) / 2, ny), name, font=fn, fill=IVORY)
    d.line([((W - 90) / 2, ny + 126), ((W + 90) / 2, ny + 126)], fill=RED, width=3)
    draw_centered(fr, dates, load(NOTO_SERIF, 34, weight=500), ny + 144, SEPIA)
    if role:
        draw_centered(fr, role, load(NOTO_SANS, 30, weight=500), ny + 192, IVORY)
    fc = load(NOTO_SANS, 20, weight=400)
    for i, c in enumerate(script.get("credit", [])):
        draw_centered(fr, c, fc, ny + 246 + i * 28, DIM)
    return fr


def ending_frame(script, portrait_img, tsec, sub, fi):
    """07 — 먹색 바탕 + 문구 + 채널명 (§11)."""
    fr = Image.new("RGB", (W, H), BLACK)
    if portrait_img is not None:                    # 초상을 아주 옅게 남겨 여운을 잇는다
        x = (W - portrait_img.width) // 2
        fr.paste(portrait_img, (x, 300))
    r0, r1 = sub["remember"]
    lines = ["오늘,", "이 이름 하나만", "기억해주세요."]
    f = load(NANUM_XBOLD, 76)
    # 문장을 읽는 속도에 맞춰 한 줄씩 떠오른다
    cum = np.cumsum([len(x) for x in lines]) / sum(len(x) for x in lines)
    speak = (tsec - r0) / max(0.1, (r1 - r0) * 0.9)
    for i, line in enumerate(lines):
        start = (cum[i - 1] if i else 0) - 0.05
        a = max(0.0, min(1.0, (speak - start) / 0.12))
        fr = with_alpha(fr, lambda im, l=line, y=1010 + i * 118: draw_centered(im, l, f, y, IVORY), a)
    a = max(0.0, min(1.0, (tsec - r1 + 0.2) / 0.5))

    def sign(im):
        d = ImageDraw.Draw(im)
        fs = load(NOTO_SERIF, 42, weight=600)
        txt = "이름을 부르다"
        tw = d.textlength(txt, font=fs)
        y = 1378
        d.text(((W - tw) / 2, y), txt, font=fs, fill=SEPIA)
        for x0, x1 in (((W - tw) / 2 - 90, (W - tw) / 2 - 24), ((W + tw) / 2 + 24, (W + tw) / 2 + 90)):
            d.line([(x0, y + 30), (x1, y + 30)], fill=SEPIA, width=1)
        draw_centered(im, "우리가 기억하는 동안 그들의 이름은 사라지지 않습니다.",
                      load(NOTO_SANS, 25, weight=400), 1446, DIM)
    return with_alpha(fr, sign, a)


# ───────────────────────── 조립 ─────────────────────────

def main():
    sp = sys.argv[1]
    script = json.load(open(os.path.join(BASE, sp), encoding="utf-8"))
    audio_dir = os.path.join(BASE, script["audio_dir"])
    tmp = os.path.join(BASE, "output/audio/_tmp_v3")
    os.makedirs(tmp, exist_ok=True)

    narration, timeline, total = build_audio(script, audio_dir, tmp)
    print(f"오디오 {total:.1f}초")
    if total > 59:
        raise SystemExit("❌ 59초를 넘습니다 — 숏츠 탭에 안 잡힙니다.")

    paper = make_paper(W, H)
    title = script.get("display_title", "")
    global COLOR_MODE
    COLOR_MODE = bool(script.get("color", False))
    # 타이틀이 커지면 사진 밴드를 그만큼 내리고 줄인다 (자막 위치 CAP_TOP은 고정)
    global PHOTO_TOP, PHOTO_H
    _, tsize = title_font(title)
    lines_n = title.count("\n") + 1
    PHOTO_TOP = int(TITLE_Y + tsize * TITLE_LINE * (lines_n - 1) + tsize + 36)
    PHOTO_H = CAP_TOP - 40 - PHOTO_TOP
    print(f"타이틀 {tsize}px · 사진 밴드 {PHOTO_TOP}~{PHOTO_TOP + PHOTO_H}")
    portrait = Portrait(os.path.join(BASE, script["portrait"]))
    ghost = portrait.img.copy()
    ghost = Image.blend(Image.new("RGB", ghost.size, BLACK), ghost, 0.22)

    silent = os.path.join(tmp, "video.mp4")
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", silent],
                           stdin=subprocess.PIPE)
    total_f = round(total * FPS)
    prev_last = None
    pool = []                                           # 회차 이미지 풀 (대본에 나온 순서)
    for x in script["segments"]:
        if x.get("image") and x["image"] not in pool and not x["image"].startswith("assets/photos"):
            pool.append(x["image"])
    used = {}
    for k, item in enumerate(timeline):
        seg, kind = item["seg"], item["seg"].get("kind", "body")
        f0, f1 = round(item["start"] * FPS), round(item["end"] * FPS)
        if k == len(timeline) - 1:
            f1 = total_f
        n = max(1, f1 - f0)
        shots = pages = font = None
        if kind == "body":
            pace = "hook" if seg["id"].startswith("01") else "normal"
            # 한 세그먼트가 SHOT_SEC보다 길면 그림을 여러 장 돌린다 (이미지 중복 사용 허용, 사용자 지시).
            # 첫 장은 대본의 image, 나머지는 회차 이미지 풀에서 아직 덜 쓴 순서로 가져온다.
            k_shots = max(1, round((n / FPS) / SHOT_SEC))
            imgs = [seg["image"]]
            while len(imgs) < k_shots:
                nxt = min(pool, key=lambda p: (used.get(p, 0), p == imgs[-1], pool.index(p)))
                imgs.append(nxt)
                used[nxt] = used.get(nxt, 0) + 1
            used[seg["image"]] = used.get(seg["image"], 0) + 1
            shots = [Shot(os.path.join(BASE, im), abs(hash(seg["id"] + im)) % 997, pace if si == 0 else "normal")
                     for si, im in enumerate(imgs)]
            pages, font = caption_pages(seg["text"])
            ai = not seg["image"].startswith("assets/photos") and not seg.get("real_photo")
            # 줄 음성 경계 → 자막 넘김 시점. 줄 수가 자막 장 수와 같을 때만 쓴다
            seg_len = item["end"] - item["start"]
            lk = [k for k in item["sub"] if k.startswith("L")]
            bounds = [(item["sub"][k][0] - item["start"]) / seg_len for k in sorted(lk, key=lambda k: int(k[1:]))] \
                if lk else None
            if bounds and len(bounds) != len(pages):
                print(f"  ⚠️ {seg['id']}: 줄 음성 {len(bounds)}개 ≠ 자막 장 {len(pages)}개 — 글자 수 비율로 넘긴다")
                bounds = None
        for i in range(n):
            fi = f0 + i
            tsec = fi / FPS
            if kind == "reveal":
                fr = reveal_frame(script, portrait, paper, title, tsec, item["sub"], fi)
            elif kind == "ending":
                fr = ending_frame(script, ghost, tsec, item["sub"], fi)
            else:
                lt = i / n
                per = n / len(shots)
                si = min(len(shots) - 1, int(i / per))
                st = (i - si * per) / per                     # 이 컷 안에서의 진행도
                fr = body_frame(paper, shots[si], seg, pages, font, st, fi, lt, title, ai, caption=False)
                # 세그먼트 안에서 그림이 바뀔 때도 크로스페이드 — **그림만** 섞는다
                j0 = i - int(si * per)
                if si > 0 and j0 < XFADE:
                    prev_fr = body_frame(paper, shots[si - 1], seg, pages, font, 1.0, fi, lt, title, ai, caption=False)
                    fr = Image.blend(prev_fr, fr, (j0 + 1) / (XFADE + 1))
            # 세그먼트 사이 크로스페이드도 자막 없는 화면끼리. 자막은 페이드가 끝난 화면 위에 얹는다
            if prev_last is not None and i < XFADE and kind in ("body", "reveal"):
                fr = Image.blend(prev_last, fr, (i + 1) / (XFADE + 1))
            if kind == "body":
                if i == n - 1:
                    prev_last = fr.copy()             # 자막 없는 마지막 화면
                fr = draw_caption_at(fr, pages, font, lt, bounds)
            elif i == n - 1:
                prev_last = fr
            enc.stdin.write(fr.tobytes())
        print(f"  {seg['id']:12s} {item['start']:5.1f}~{item['end']:5.1f}s")
    enc.stdin.close()
    enc.wait()

    bgm = os.path.join(audio_dir, "bgm_v3.wav")
    name_at = build_bgm(bgm, total, timeline, script)
    mixed = os.path.join(audio_dir, "mixed_v3.wav")
    ff(["-i", narration, "-i", bgm, "-filter_complex",
        f"[0:a]volume=1.0[v];[1:a]volume={script.get('bgm_gain', 0.9)}[b];"
        "[v][b]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        "loudnorm=I=-14:TP=-1.5:LRA=11,aformat=channel_layouts=stereo",
        "-ar", "48000", mixed])
    out = os.path.join(BASE, script["output"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    ff(["-i", silent, "-i", mixed, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", out])
    print(f"saved {out}  ({total:.1f}s, 이름 {name_at:.1f}s)")


if __name__ == "__main__":
    main()
