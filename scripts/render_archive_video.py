"""'이름을 부르다' 시리즈 영상 렌더러.

- 자막은 타자기처럼 한 글자씩 찍힌다 (나레이션보다 먼저 끝나도록 동기화)
- 컷 전환은 책장이 넘어가듯 인화지가 세로축으로 접히며 사라진다
"""
import json
import math
import os
import subprocess
import sys

from PIL import Image, ImageEnhance, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archive_layout import (  # noqa: E402
    BOTTOM_SAFE, H, NOTO_SERIF, PHOTO_TOP, W,
    build_card, caption_lines, card_pos, draw_caption, draw_year,
    load, make_paper, paste_card,
)

FPS = 30
CAP_SIZE = 46
CAP_WEIGHT = 400
TYPE_RATIO = 0.6      # 나레이션 길이의 60% 지점에서 타이핑 완료
FLIP_FRAMES = 14      # 페이지 넘김에 쓰는 프레임 수

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def _ease_out(t, p=3):
    return 1 - (1 - t) ** p


def _ease_in_out(t):
    """부드럽게 출발해 사뿐히 멈추는 곡선(smoothstep).

    ease-out은 시작하자마자 확 떨어져서 '후다닥' 느낌이 난다.
    내려앉는 연출에는 양끝이 모두 완만한 이 곡선이 맞다.
    """
    return t * t * (3 - 2 * t)


def _shadow(card_mask, blur=24, alpha=0.78, off=(40, 46), pad=80):
    sh = Image.new("L", (card_mask.width + pad, card_mask.height + pad), 0)
    sh.paste(card_mask, off)
    return sh.filter(ImageFilter.GaussianBlur(blur)).point(lambda p: int(p * alpha))


def drop_layer(canvas, card, mask, pos, p, rise=140, tilt=3.5):
    """진행도 p(0~1)에서 카드가 내려앉는 모습을 canvas 위에 합성한다.

    세그먼트 사이 전환과 세그먼트 도중 사진 교체가 같은 동작을 써야 하므로
    한 프레임 단위로 떼어 두 곳에서 공유한다.

    낙하 높이(rise)를 260에서 140으로 줄이고 **떨어지면서 서서히 나타나게** 했다.
    260이면 낙하 중 카드가 상단 타이틀·연도 위를 지나가며 글자를 덮어버린다
    (밝은 인화지 위에 어두운 글자가 얹혀 읽히지 않았다).
    """
    t = _ease_in_out(p)
    ang = tilt * (1 - t)                       # 기울어진 채 내려와 수평으로 안착
    c = card.rotate(ang, resample=Image.BICUBIC, expand=True)
    m = mask.rotate(ang, resample=Image.BICUBIC, expand=True)
    if t < 1.0:                                # 안착하면서 또렷해진다
        m = m.point(lambda v: int(v * t))

    x = pos[0] - (c.width - card.width) // 2
    y = int(pos[1] - (c.height - card.height) // 2 - rise * (1 - t))

    # 가까워질수록 그림자가 좁고 진해진다
    lift = 1 - t
    sh = _shadow(m, blur=int(24 + 40 * lift), alpha=0.78 - 0.2 * lift,
                 off=(40, int(46 + 40 * lift)))
    canvas.paste(Image.new("RGB", sh.size, (0, 0, 0)), (x - 40, y - 40), sh)
    canvas.paste(c, (x, y), m)
    return canvas


def fade_out_amount(p, fade_start=0.3):
    """낙하 초반에는 이전 장을 남겨 겹쳐 보이게 하고, 후반에 걷어낸다."""
    return 0.0 if p <= fade_start else _ease_in_out((p - fade_start) / (1 - fade_start))


def trans_drop_frame(paper, old_canvas, new_card, new_mask, i, n=32):
    """전환 i번째 프레임 한 장만 만든다.

    예전에는 32장을 리스트로 만들어 들고 있었는데, 1080×1920 RGB 32장이면
    200MB 가까이 된다. 렌더 도중 시스템 메모리 부족으로 프로세스가 죽는 원인이었다.
    프레임끼리 의존이 없으므로 그때그때 만들어 쓰고 버린다.
    """
    p = (i + 1) / n
    frame = Image.blend(paper, old_canvas, 1.0 - fade_out_amount(p))
    return drop_layer(frame, new_card, new_mask, card_pos(new_card), p)


def trans_drop(paper, old_canvas, new_card, new_mask, n=32):
    """새 사진이 위에서 비스듬히 내려와 앉고, 그 사이 이전 화면은 스르륵 사라진다."""
    return [trans_drop_frame(paper, old_canvas, new_card, new_mask, i, n)
            for i in range(n)]


def trans_slide(base_canvas, old_card, old_mask, n=16, dist=None):
    """이전 사진을 옆으로 밀어내 아래 사진을 드러낸다. (책상 위 자료를 치우는 느낌)"""
    x0, y0 = card_pos(old_card)
    dist = dist or (x0 + old_card.width + 60)
    out = []
    for i in range(n):
        t = _ease_out((i + 1) / n, 2)
        frame = base_canvas.copy()
        x = int(x0 - dist * t)
        sh = _shadow(old_mask)
        frame.paste(Image.new("RGB", sh.size, (0, 0, 0)), (x - 40, y0 - 40), sh)
        frame.paste(old_card, (x, y0), old_mask)
        out.append(frame)
    return out


def trans_dissolve(old_canvas, new_canvas, n=16):
    """크로스 디졸브 — 역사 다큐의 표준 전환."""
    return [Image.blend(old_canvas, new_canvas, _ease_out((i + 1) / n, 2)) for i in range(n)]


def kenburns(card, mask, t, zoom=0.06):
    """아주 느린 줌. 사진만이 아니라 찢긴 인화지 전체가 통째로 커진다.

    되잘라내면 찢긴 가장자리가 깎여나가므로, 확대한 결과를 그대로 쓰고
    붙일 위치를 중심 기준으로 다시 잡는다(-> kb_pos).
    """
    s = 1 + zoom * t
    cw, ch = int(card.width * s), int(card.height * s)
    return card.resize((cw, ch), Image.LANCZOS), mask.resize((cw, ch), Image.LANCZOS)


def kb_pos(orig_card, grown_card):
    """확대된 인화지를 원래 중심에 맞춰 놓기 위한 좌표."""
    x0, y0 = card_pos(orig_card)
    cx = x0 + orig_card.width / 2
    cy = y0 + orig_card.height / 2
    return int(cx - grown_card.width / 2), int(cy - grown_card.height / 2)


def render(script_path, images, out_path, audio_dir=None, fallback_sec=3.4):
    script = json.load(open(script_path, encoding="utf-8"))
    font = load(NOTO_SERIF, CAP_SIZE, weight=CAP_WEIGHT)

    paper = make_paper(W, H)
    frames_dir = os.path.join(BASE, "output/video/frames")
    os.makedirs(frames_dir, exist_ok=True)
    for f in os.listdir(frames_dir):
        os.remove(os.path.join(frames_dir, f))

    idx = 0
    prev = None       # (canvas, card, mask)
    for seg in script["segments"]:
        photo = images.get(seg["id"])
        if photo is None:
            continue

        card, mask, graded = build_card(photo, seed=abs(hash(seg["id"])) % 997)
        canvas = paste_card(paper.copy(), card, mask, graded)
        draw_year(canvas, seg.get("year", script.get("year", "")))

        # --- 컷 전환: 이전 장을 넘긴다 ---
        if prev is not None:
            for fr in flip_frames(paper, prev[1], prev[2], canvas):
                fr.save(os.path.join(frames_dir, f"{idx:05d}.png"))
                idx += 1

        # --- 타이핑 ---
        dur = seg.get("duration")
        if dur is None and audio_dir:
            wav = os.path.join(audio_dir, f"{seg['id']}.wav")
            if os.path.exists(wav):
                import contextlib
                import wave
                with contextlib.closing(wave.open(wav)) as w:
                    dur = w.getnframes() / w.getframerate()
        dur = dur or fallback_sec

        lines = caption_lines(seg["text"], font)
        total = len(("".join(lines)))
        n = max(1, int(dur * FPS))
        type_n = max(1, int(n * TYPE_RATIO))

        for i in range(n):
            reveal = total if i >= type_n else int(total * (i / type_n))
            fr = draw_caption(canvas.copy(), lines, font, CAP_SIZE,
                              reveal=reveal, cursor=i < type_n)
            fr.save(os.path.join(frames_dir, f"{idx:05d}.png"))
            idx += 1

        prev = (canvas, card, mask)

    print(f"{idx} frames -> {out_path}")
    cmd = ["ffmpeg", "-y", "-framerate", str(FPS),
           "-i", os.path.join(frames_dir, "%05d.png"),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", out_path]
    subprocess.run(cmd, check=True, capture_output=True)
    print("done.")


if __name__ == "__main__":
    render(
        script_path=os.path.join(BASE, "drafts/script_dok_01_kang.json"),
        images={
            "01_hook": os.path.join(BASE, "output/images/kang_01_station.png"),
            "03_setup": os.path.join(BASE, "output/images/kang_02_aftermath.png"),
        },
        out_path=os.path.join(BASE, "output/video/archive_motion_test.mp4"),
    )
