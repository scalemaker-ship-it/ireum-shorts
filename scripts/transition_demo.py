"""전환 방식 3종 비교 데모 — 사진 얹기 / 옆으로 빼내기 / 크로스 디졸브."""
import os
import subprocess
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archive_layout import (  # noqa: E402
    NOTO_SERIF, build_card, caption_lines, card_pos, draw_caption, draw_year,
    load, make_paper, paste_card,
)
from render_archive_video import (  # noqa: E402
    CAP_SIZE, CAP_WEIGHT, FPS, kb_pos, kenburns, trans_drop,
)

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
HOLD = 95          # 느린 줌이 체감되도록 충분히 머문다 (약 3.2초)
TRANS_N = 32       # 사진이 내려앉는 시간 (약 1.07초)


def frame_at(paper, card, mask, graded, year, caption, font, t):
    """줌 진행도 t(0~1) 시점의 한 프레임. 인화지 전체가 통째로 커진다."""
    c, m = kenburns(card, mask, t)
    fr = paste_card(paper.copy(), c, m, graded, pos=kb_pos(card, c))
    draw_year(fr, year)
    draw_caption(fr, caption_lines(caption, font), font, CAP_SIZE)
    return fr


def main():
    font = load(NOTO_SERIF, CAP_SIZE, weight=CAP_WEIGHT)
    paper = make_paper(1080, 1920)

    p1 = os.path.join(BASE, "output/images/kang_01_station.png")
    p2 = os.path.join(BASE, "output/images/kang_02_aftermath.png")
    c1 = "1919년 9월 2일 오후 다섯 시. 경성 남대문역에 폭탄이 터졌다."
    c2 = "총독은 살아남았다. 대신 그를 맞으러 나온 서른 명 남짓이 쓰러졌다."

    card1, mask1, g1 = build_card(p1, seed=311)
    card2, mask2, g2 = build_card(p2, seed=577)

    frames_dir = os.path.join(BASE, "output/video/frames_demo")
    os.makedirs(frames_dir, exist_ok=True)
    for f in os.listdir(frames_dir):
        os.remove(os.path.join(frames_dir, f))

    seq = []

    # 1컷: 느린 줌으로 서서히 커진다
    for i in range(HOLD):
        seq.append(frame_at(paper, card1, mask1, g1, 1919, c1, font, i / (HOLD - 1)))

    # 전환: 새 사진이 내려앉는 동안 이전 장은 스르륵 걷힌다
    seq += trans_drop(paper, seq[-1], card2, mask2, TRANS_N)

    # 2컷: 다시 처음 크기에서 서서히 커진다
    for i in range(HOLD):
        seq.append(frame_at(paper, card2, mask2, g2, 1919, c2, font, i / (HOLD - 1)))

    print(f"{len(seq)} frames")
    for i, fr in enumerate(seq):
        fr.save(os.path.join(frames_dir, f"{i:05d}.png"))

    out = os.path.join(BASE, "output/video/transition_demo.mp4")
    subprocess.run(["ffmpeg", "-y", "-framerate", str(FPS),
                    "-i", os.path.join(frames_dir, "%05d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", out],
                   check=True, capture_output=True)
    print("saved", out)


if __name__ == "__main__":
    main()
