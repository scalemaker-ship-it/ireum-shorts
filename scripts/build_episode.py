"""'이름을 부르다' 1화 완성본 빌드.

핵심 설계: 전환은 시간을 추가로 쓰지 않는다.
사진이 내려앉는 동안에도 나레이션은 계속 흐르므로, 전환 프레임을 세그먼트
길이 안쪽에 포함시킨다. (전환을 세그먼트 사이에 끼워 넣으면 그만큼 영상이
길어져 숏츠 60초 제한을 넘긴다.)
"""
import contextlib
import json
import os
import re
import subprocess
import sys
import wave

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archive_layout import (  # noqa: E402
    H, NOTO_SERIF, PHOTO_BORDER, PHOTO_TOP, W, caption_pages, card_pos, draw_caption, draw_credit,
    draw_nameplate, draw_title, draw_year, load, make_paper, page_at, paste_card,
)
from render_archive_video import (  # noqa: E402
    CAP_SIZE, CAP_WEIGHT, FPS, trans_drop_frame,
)
import impact_fx as IMPACT  # noqa: E402
import live_card as LIVE  # noqa: E402

# 장면별 움직임. 대본 세그먼트의 "fx" 값으로 고른다.
# 연기 세기는 실측으로 정했다 — 0.55는 너무 셌고(평균 차이 15.8) 0.18이 적당하다(5.0).
FX_KINDS = {
    "smoke":        lambda: LIVE.smoke(0.18, 150),
    "smoke_soft":   lambda: LIVE.smoke(0.12, 100),
    "dust":         lambda: LIVE.dust(),
    "flicker":      lambda: LIVE.flicker(0.07, 0.8),
    "flicker_soft": lambda: LIVE.flicker(0.045, 0.6),
}

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SPEED = 1.15          # 나레이션 배속 (잡학쿠키 1.3배속보다 느리게)
TRANS_N = 32          # 사진이 내려앉는 프레임 수 (약 1.07초)
# 자막은 세그먼트 0프레임부터 글자 수에 비례해 찍는다. TTS가 거의 일정한 속도로
# 읽으므로 이렇게 하면 음성과 맞는다. 끝에 여유를 두는 건 TTS 끝의 무음 때문.
TYPE_RATIO = 0.88
ZOOM = 0.06
NAMEPLATE = ("강우규", "1855 – 1920")
SERIES_TITLE = "누가 총독에게 폭탄을 던졌나"   # 회차별 후킹 소제목 (반전 정보 금지)

# 마지막 추모 컷에 넣는 출처. 60초 제한 탓에 별도 출처 카드를 둘 수 없어
# 초상 화면의 이름표 아래 빈 공간을 쓴다. 상세 출처는 영상 설명란에 적는다.
CREDIT = [
    "자료 · 국가보훈부 공훈전자사료관, 한국민족문화대백과사전",
    "사진 · 위키미디어 커먼즈 (퍼블릭 도메인)",
]
SILENCE_BEFORE = "06_reveal"   # 반전 직전 정적
SILENCE_SEC = 0.5
PAUSE_AFTER = {
    "02_brand": 1.4,    # 채널명 뒤 한 박자
    "06_reveal": 1.2,   # 이름을 부른 뒤 여운
}

PORTRAIT = "assets/photos/kang_woogyu_portrait.jpg"   # 퍼블릭 도메인 실제 초상

IMAGES = {   # BASE 기준 경로
    "01_hook":   "output/images/kang_01_station.png",
    "02_brand":  "output/images/kang_03_ledger.png",
    "03_setup":  "output/images/kang_02_aftermath.png",
    "04_hint1":  "output/images/kang_04_street.png",
    "05_hint2":  "output/images/kang_05_patrol.png",
    "06_reveal": "output/images/kang_06_herbshop.png",
    "07_echo":   "output/images/kang_07_rails.png",
    "08_quote":  "output/images/kang_08_prison.png",
    "09_cta":    PORTRAIT,          # 마무리는 초상 앞에서 이름을 부른다
}

# 이름표를 붙일 세그먼트 (초상이 나오는 구간)
PLATE_ON = {"09_cta"}

# 반전 세그먼트에서 이름이 실제로 불리는 지점 (BGM 스팅을 여기 맞춘다)
NAME_AT = 0.75

PLATE_H = 128          # 카드 아래 → 출처 첫 줄까지 (이름 + 생몰년)
CREDIT_LINE = 32       # 출처 줄 간격


SEG_TARGET_DB = -26.0   # 세그먼트별로 맞출 평균 레벨
# 사운드 로고는 나레이션보다 낮게 깔린다. 같은 -26dB로 맞추면 종소리가 말만큼
# 커져서 귀를 때린다(음성은 무음 구간이 섞여 평균이 낮고, 종은 계속 울린다).
LOGO_TARGET_DB = -30.0

# TTS는 문장 끝에 0.2~0.5초씩 무음을 붙여준다. 세그먼트가 10개면 편당 2.5초가
# **의도하지 않은 늘어짐**으로 쌓인다(실측 1~5화 2.2~2.7초). 설계된 정적
# (반전 앞 0.5 / 채널명 뒤 1.4 / 이름 뒤 1.4)과 달리 이건 그냥 빈 시간이다.
# 목소리 속도를 올리면 이 채널이 파는 진중함이 깎이므로, 대신 이걸 걷어낸다.
TAIL_KEEP = 0.15       # 발화가 끝난 뒤 남길 여운 (초)

# 실측해 보니 나레이션 트랙의 34%가 무음이고, 그중 **13.7초가 문장과 문장 사이**였다
# (1화 기준). TTS가 마침표마다 0.4~0.6초를 넣는다. 끝 무음(0.5초)은 곁가지였다.
# 여기를 조이면 목소리 속도를 올리지 않고도 속도감이 붙는다 —
# 1.15배속을 유지해야 이 채널이 파는 진중함이 안 깎인다.
GAP_MAX = 0.28         # 문장 사이 무음 상한 (초). None이면 손대지 않는다


def voiced_end(p, rel=0.02):
    """발화가 실제로 끝나는 지점."""
    import struct
    with contextlib.closing(wave.open(p)) as w:
        sr, n = w.getframerate(), w.getnframes()
        d = struct.unpack(f"<{n}h", w.readframes(n))
    thr = (max(abs(x) for x in d) or 1) * rel
    i = n - 1
    while i > 0 and abs(d[i]) < thr:
        i -= 1
    return i / sr


def wav_dur(p):
    with contextlib.closing(wave.open(p)) as w:
        return w.getnframes() / w.getframerate()


def mean_db(p):
    o = subprocess.run(["ffmpeg", "-i", p, "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    m = re.search(r"mean_volume: (-?[\d.]+)", o)
    return float(m.group(1)) if m else SEG_TARGET_DB


def build_audio(script, audio_dir, out_wav):
    """세그먼트를 배속 처리해 이어 붙이고, 반전 직전에 정적을 넣는다."""
    tmp = os.path.join(BASE, "output/audio/_tmp")
    os.makedirs(tmp, exist_ok=True)
    parts, durs = [], {}

    # 배속은 **대본별로 정한다.** 전역 상수 하나로 두면 새 배속을 시험할 때
    # 이미 낸 회차까지 같이 바뀐다(1~10화는 1.15배속으로 확정된 상태다).
    # 2026-09-18 유지율 개선 작업에서 '더 빠르게'를 시험하며 분리했다.
    speed = float(script.get("playback_speed", SPEED))

    sil = os.path.join(tmp, "silence.wav")
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-t", str(SILENCE_SEC),
                    "-i", "anullsrc=r=44100:cl=mono", sil],
                   check=True, capture_output=True)

    def make_silence(sec, name):
        p = os.path.join(tmp, name)
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-t", str(sec),
                        "-i", "anullsrc=r=44100:cl=mono", p],
                       check=True, capture_output=True)
        return p

    # ⚠️ 세그먼트 id를 재배치하면 오디오 파일이 조용히 어긋난다.
    # 17화에서 실제로 났다 — 컷을 끼우며 03→04, 04→04b로 밀었더니 04b의 wav가 없고
    # 04_hint1.wav에는 04b의 음성이 들어 있었다. ffmpeg가 "exit status 254"로만 죽어
    # 원인을 찾는 데 시간이 걸렸다. 여기서 먼저 잡고 무엇이 없는지 이름을 찍는다.
    missing = [seg["id"] for seg in script["segments"]
               if not seg.get("locked_audio")
               and not os.path.exists(os.path.join(audio_dir, f"{seg['id']}.wav"))]
    if missing:
        raise SystemExit(
            "❌ 음성이 없는 세그먼트: " + ", ".join(missing) + "\n"
            f"   {audio_dir} 를 확인하세요.\n"
            "   대본에서 세그먼트 id를 바꿨다면 wav 파일명도 같이 바꿔야 합니다.\n"
            "   고친 문장만 다시 뽑기: "
            "python3 scripts/generate_tts.py <대본> <audio_dir> <id,id,...>")

    leads, hits = {}, {}
    for seg in script["segments"]:
        dst = os.path.join(tmp, f"{seg['id']}.wav")
        # locked_audio: 사용자가 고른 테이크를 조립해 둔 음성. 사이(pause)까지 계산해
        # 만든 것이므로 배속을 다시 걸면 의도한 템포가 망가진다. 레벨만 맞춘다.
        locked = seg.get("locked_audio")
        src = os.path.join(BASE, locked) if locked else \
            os.path.join(audio_dir, f"{seg['id']}.wav")

        # TTS는 호출마다 출력 레벨이 달라진다(실측 -28~-35dB). 그대로 이어붙이면
        # 세그먼트가 바뀔 때마다 목소리 크기가 튄다. 배속과 함께 레벨도 맞춘다.
        # 사운드 로고는 말이 아니다. 음성용 레벨(-26dB)로 정규화하면 종소리가
        # 나레이션만큼 커져 귀를 때린다. 목표 레벨을 따로 두고 배속·무음 제거도 건너뛴다.
        # (2026-09-18 C안 — 브랜드 나레이션을 걷어낸 자리에 들어가는 소리다)
        if seg.get("kind") == "logo":
            af = f"volume={LOGO_TARGET_DB - mean_db(src):+.2f}dB"
            subprocess.run(["ffmpeg", "-y", "-i", src, "-filter:a", af,
                            "-ar", "44100", "-ac", "1", dst], check=True, capture_output=True)
            parts.append(dst)
            durs[seg["id"]] = wav_dur(dst)
            if seg["id"] in PAUSE_AFTER:
                parts.append(make_silence(PAUSE_AFTER[seg["id"]], f"pause_{seg['id']}.wav"))
            continue

        gain = SEG_TARGET_DB - mean_db(src)
        if locked:
            af = f"volume={gain:+.2f}dB"      # 확정 테이크는 사이까지 계산해 만든 것
        else:
            af = f"atempo={speed},volume={gain:+.2f}dB"
            if GAP_MAX:
                af += (f",silenceremove=stop_periods=-1"
                       f":stop_duration={GAP_MAX}:stop_threshold=-45dB")
        subprocess.run(["ffmpeg", "-y", "-i", src, "-filter:a", af,
                        "-ar", "44100", "-ac", "1", dst], check=True, capture_output=True)

        # 확정 테이크는 사이까지 계산해 만든 것이라 건드리지 않는다.
        # 나머지는 TTS가 붙인 끝 무음을 걷어낸다.
        if not locked and TAIL_KEEP is not None:
            ve = voiced_end(dst)
            if wav_dur(dst) - ve > TAIL_KEEP + 0.02:
                cut = os.path.join(tmp, f"{seg['id']}_t.wav")
                subprocess.run(["ffmpeg", "-y", "-i", dst, "-t", f"{ve + TAIL_KEEP:.3f}",
                                "-ar", "44100", "-ac", "1", cut],
                               check=True, capture_output=True)
                os.replace(cut, dst)

        # 사건이 일어나는 컷에는 소리를 **나레이션 앞에** 둔다.
        # 회차당 한 번만 쓴다 — 흔하면 순국을 다루는 톤이 액션 편집처럼 깨진다.
        imp = seg.get("impact")
        if imp:
            sfx = getattr(IMPACT, imp.get("sound", "explosion"))(
                os.path.join(tmp, f"sfx_{seg['id']}.wav"))
            wip = os.path.join(tmp, f"imp_{seg['id']}.wav")
            if "at_sentence" in imp:
                # 문장이 사건을 말하는 순간에 얹는다. 앞에 붙이면 맥락 없는 굉음이 된다.
                at = IMPACT.sentence_end(dst, imp["at_sentence"]) or 0.0
                IMPACT.overlay(sfx, dst, wip, at=at, sfx_db=imp.get("db", -6))
                hits[seg["id"]] = at
            else:
                lead = imp.get("lead", 0.9)
                IMPACT.prepend(sfx, dst, wip, lead=lead, sfx_db=imp.get("db", -6))
                leads[seg["id"]] = lead
                hits[seg["id"]] = 0.0
            os.replace(wip, dst)

        if seg["id"] == SILENCE_BEFORE:
            parts.append(sil)
        parts.append(dst)
        durs[seg["id"]] = wav_dur(dst)
        if seg["id"] in PAUSE_AFTER:
            parts.append(make_silence(PAUSE_AFTER[seg["id"]], f"pause_{seg['id']}.wav"))

    lst = os.path.join(tmp, "concat.txt")
    with open(lst, "w") as f:
        for p in parts:
            f.write(f"file '{os.path.abspath(p)}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c", "copy", out_wav], check=True, capture_output=True)
    return durs, wav_dur(out_wav), leads, hits


def main():
    # 회차 설정은 전부 대본 JSON에서 읽는다. 스크립트를 회차마다 고치지 않기 위함.
    sp = sys.argv[1] if len(sys.argv) > 1 else "drafts/script_dok_01_kang.json"
    script = json.load(open(os.path.join(BASE, sp), encoding="utf-8"))

    global SERIES_TITLE, NAMEPLATE, CREDIT, SILENCE_BEFORE, PAUSE_AFTER, NAME_AT, IMAGES, PLATE_ON
    global SILENCE_SEC
    SERIES_TITLE = script.get("display_title", SERIES_TITLE)
    NAMEPLATE = tuple(script.get("nameplate", NAMEPLATE))
    CREDIT = script.get("credit", CREDIT)
    SILENCE_BEFORE = script.get("silence_before", SILENCE_BEFORE)
    PAUSE_AFTER = script.get("pause_after", PAUSE_AFTER)
    # 정적도 배속을 따라간다. 말만 빠르게 하고 쉼을 그대로 두면 쉼이 상대적으로 길어진다
    # (11화에서 1.25배속으로 올린 뒤 "이름 뒤 텀이 길다"는 지적을 받았다).
    SILENCE_SEC = float(script.get("silence_sec", SILENCE_SEC))
    NAME_AT = script.get("name_at", NAME_AT)
    # 빈 인화지를 쓰면서 사유 표기가 없으면 시청자는 그 빈 화면이 의도인지 사고인지
    # 알 수 없다(PRD 5항). 11~20화 아홉 편에서 통째로 빠진 적이 있어 렌더 단계에서 막는다.
    _cta = next((x for x in script["segments"] if x["id"] == "09_cta"), None)
    if _cta and "blank_plate" in str(_cta.get("image", "")):
        if not any(str(c).startswith("전하는 사진이") for c in CREDIT):
            raise SystemExit(
                "❌ 빈 인화지를 쓰는데 초상 미확보 표기가 없습니다.\n"
                "   대본 credit 첫 줄에 넣으세요: "
                "'전하는 사진이 확인되지 않아 빈 인화지로 둡니다'")

    if any("image" in x for x in script["segments"]):
        IMAGES = {x["id"]: x["image"] for x in script["segments"]}
        PLATE_ON = {x["id"] for x in script["segments"] if x.get("nameplate")}

    audio_dir = os.path.join(BASE, script.get("audio_dir", "output/audio/dok_01"))
    os.makedirs(audio_dir, exist_ok=True)
    out_wav = os.path.join(audio_dir, "narration.wav")
    durs, total, leads, hits = build_audio(script, audio_dir, out_wav)
    print(f"오디오 {total:.1f}초")

    font = load(NOTO_SERIF, CAP_SIZE, weight=CAP_WEIGHT)
    paper = make_paper(W, H)
    frames_dir = os.path.join(BASE, "output/video/_frames")
    os.makedirs(frames_dir, exist_ok=True)
    for f in os.listdir(frames_dir):
        os.remove(os.path.join(frames_dir, f))

    idx = 0
    prev_canvas = None
    prev_nocap = None

    for seg in script["segments"]:
        img = os.path.join(BASE, IMAGES[seg["id"]])
        # 자막이 길면 글자를 줄이지 않고 **다음 장으로 넘긴다.**
        pages, counts, font, cap_top = caption_pages(seg["text"], CAP_SIZE, CAP_WEIGHT)

        # 추모 컷은 사진 아래에 이름표(2줄)와 출처가 붙는다. 사진을 그대로 두면
        # 그 블록이 자막을 밀고 들어간다(사진을 내린 뒤 실제로 34px 겹쳤다).
        # 블록이 자막 위끝 안에 들어가도록 **사진 높이를 거꾸로 계산해 제한한다.**
        max_h = None
        if seg["id"] in PLATE_ON:
            max_h = (cap_top - 20 - PLATE_H - CREDIT_LINE * len(CREDIT)
                     - PHOTO_TOP - PHOTO_BORDER * 2)

        # 인화지 틀은 고정하고 **사진 안에서 카메라가 움직인다**(live_card).
        # 예전에는 카드 전체가 6% 커졌는데, 그건 사진이 부푸는 것이지 카메라 워크가 아니었다.
        prep = LIVE.prepare(img, seed=abs(hash(seg["id"])) % 997, max_h=max_h)
        fx = FX_KINDS[seg["fx"]]() if seg.get("fx") in FX_KINDS else None
        moving = seg.get("motion", True)
        lead_f = int(leads.get(seg["id"], 0.0) * FPS)   # 효과음이 먼저 나는 구간
        if len(pages) > 1:
            print(f"  {seg['id']}: 자막 {sum(len(p) for p in pages)}줄 → {len(pages)}장으로 나눔 "
                  f"({'+'.join(str(len(p)) for p in pages)}줄)")
        total_chars = sum(counts)

        n = max(1, round(durs[seg["id"]] * FPS))
        # 반전 직전 정적 구간은 이전 화면을 그대로 유지한다
        if seg["id"] == SILENCE_BEFORE and prev_canvas is not None:
            for _ in range(round(SILENCE_SEC * FPS)):
                prev_canvas.save(os.path.join(frames_dir, f"{idx:05d}.png"))
                idx += 1

        trans_n = min(TRANS_N, max(0, n - 4)) if prev_canvas is not None else 0

        type_n = max(1, int(n * TYPE_RATIO))
        points = seg.get("reveal_points")

        for i in range(n):
            # 효과음이 울리는 동안은 카메라를 세워두고, 말이 시작되면 움직인다
            span = max(1, n - 1 - lead_f)
            t = min(1.0, max(0.0, (i - lead_f) / span)) if moving else 0.5
            c, m, view = LIVE.frame_at(prep, t, fx, i)
            plate_alpha = 1.0 if seg["id"] in PLATE_ON else 0.0
            plate_card, plate_pos = c, card_pos(c)

            if i < trans_n:
                fr = trans_drop_frame(paper, prev_nocap, c, m, i, trans_n)
            else:
                fr = paste_card(paper.copy(), c, m, view, pos=card_pos(c))

            draw_title(fr, SERIES_TITLE)
            draw_year(fr, seg["year"])
            if plate_alpha > 0:
                a = min(1.0, plate_alpha)
                fr = draw_nameplate(fr, plate_card, plate_pos, *NAMEPLATE, alpha=a)
                fr = draw_credit(fr, plate_card, plate_pos, CREDIT, alpha=a)

            # 자막은 0프레임부터 글자 수에 비례해 찍는다 (음성과 동기).
            # 문장 사이에 의도적인 사이가 있는 세그먼트는 균등 배분이 어긋나므로
            # reveal_points([진행비율, 누적글자수])로 실제 발화 시점을 따라간다.
            if points:
                p_t = i / max(1, n - 1)
                reveal, prev_t, prev_c = total_chars, 0.0, 0
                for pt, pc in points:
                    if p_t <= pt:
                        span = max(pt - prev_t, 1e-6)
                        reveal = int(prev_c + (pc - prev_c) * (p_t - prev_t) / span)
                        break
                    prev_t, prev_c = pt, pc
            else:
                j = max(0, i - lead_f)
                tn = max(1, type_n - lead_f)
                # 로고 컷은 0.8초뿐이라 한 글자씩 찍으면 어수선하다. 통째로 띄운다.
                reveal = (total_chars if (seg.get("kind") == "logo" or j >= tn)
                          else int(total_chars * (j / tn)))
            pi, r_in = page_at(counts, reveal)
            draw_caption(fr, pages[pi], font, CAP_SIZE, reveal=r_in,
                         cursor=reveal < total_chars, top=cap_top)

            # 소리가 난 직후 짧게 흔들린다. 오래 흔들면 멀미가 난다.
            imp = seg.get("impact")
            if imp and imp.get("shake"):
                # 흔들림은 소리가 난 순간부터 시작한다
                dx, dy = IMPACT.shake(i / FPS - hits.get(seg["id"], 0.0), FPS,
                                      amp=imp["shake"], decay=6.5)
                if dx or dy:
                    sh = Image.new("RGB", (W, H), (9, 8, 7))
                    sh.paste(fr, (dx, dy))
                    fr = sh

            fr.save(os.path.join(frames_dir, f"{idx:05d}.png"))
            idx += 1

        prev_canvas = fr
        # 다음 전환에 쓸 '자막 없는' 화면을 따로 만들어 둔다
        c, m, view = LIVE.frame_at(prep, 1.0 if moving else 0.5, fx, n)
        prev_nocap = paste_card(paper.copy(), c, m, view, pos=card_pos(c))
        draw_title(prev_nocap, SERIES_TITLE)
        draw_year(prev_nocap, seg["year"])

        # 채널명 뒤 한 박자 — 화면을 그대로 붙잡는다
        if seg["id"] in PAUSE_AFTER:
            for _ in range(round(PAUSE_AFTER[seg["id"]] * FPS)):
                fr.save(os.path.join(frames_dir, f"{idx:05d}.png"))
                idx += 1

    print(f"{idx} 프레임 ({idx / FPS:.1f}초)")

    # --- BGM 합성 후 나레이션과 믹스 ---
    video_sec = idx / FPS

    # 스팅은 세그먼트 시작이 아니라 '이름이 불리는 순간'(초상 등장)에 맞춘다
    ids = [s["id"] for s in script["segments"]]
    upto = ids[:ids.index(SILENCE_BEFORE)]
    reveal_at = (sum(durs[i] for i in upto)
                 + sum(PAUSE_AFTER.get(i, 0) for i in upto)
                 + SILENCE_SEC
                 + durs[SILENCE_BEFORE] * NAME_AT)
    bgm = os.path.join(BASE, audio_dir, "bgm.wav")
    subprocess.run([sys.executable, os.path.join(BASE, "scripts/make_bgm.py"),
                    f"{video_sec:.2f}", f"{reveal_at:.2f}", bgm],
                   check=True, capture_output=True)

    # amix는 기본적으로 입력 개수만큼 볼륨을 나눠버린다(normalize=0으로 끔).
    # 그 뒤 loudnorm으로 유튜브 기준(-14 LUFS)에 맞춘다. 이걸 빼면 다른 숏츠보다
    # 확연히 작게 들린다.
    mixed = os.path.join(audio_dir, "mixed.wav")
    subprocess.run(["ffmpeg", "-y", "-i", out_wav, "-i", bgm,
                    "-filter_complex",
                    "[0:a]volume=1.0[v];[1:a]volume=0.9[b];"
                    "[v][b]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
                    "loudnorm=I=-14:TP=-1.5:LRA=11,aformat=channel_layouts=stereo",
                    "-ar", "48000",   # loudnorm이 96k로 올려놓는 걸 되돌린다
                    mixed], check=True, capture_output=True)

    out = sys.argv[2] if len(sys.argv) > 2 else \
        os.path.join(BASE, script.get("output", "output/최종본/dok_01_kang.mp4"))
    subprocess.run(["ffmpeg", "-y", "-framerate", str(FPS),
                    "-i", os.path.join(frames_dir, "%05d.png"), "-i", mixed,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", out],
                   check=True, capture_output=True)
    print(f"saved {out}  (BGM 스팅 {reveal_at:.1f}s)")


if __name__ == "__main__":
    main()
