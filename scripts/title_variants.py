"""상단 타이틀 후보 비교 — 채널명 고정 vs 회차별 소제목."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archive_layout import (  # noqa: E402
    NOTO_SERIF, W, H, build_card, caption_lines, draw_caption, draw_title, draw_year,
    load, make_paper, paste_card,
)

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CAP = "폭탄을 던진 사람은 예순다섯이었다. 1855년에 태어나, 평생 약을 지어온 한의사였다. 그의 이름은, 강우규."

VARIANTS = {
    "H1_question": "누가 총독에게 폭탄을 던졌나",   # 직접 질문 — 영상이 곧 답
    "H2_days":     "보름 동안 잡히지 않았다",       # 사실 기반 긴장
    "H3_blockade": "경성을 봉쇄하고도 놓쳤다",      # 규모 + 실패
    "H4_wrong":    "경찰은 잘못 찾고 있었다",       # 오인 프레임
}


def main():
    font = load(NOTO_SERIF, 46, weight=400)
    paper = make_paper(W, H)
    card, mask, graded = build_card(
        os.path.join(BASE, "output/images/kang_06_herbshop.png"), seed=311)

    for name, title in VARIANTS.items():
        fr = paste_card(paper.copy(), card, mask, graded)
        draw_title(fr, title)
        draw_year(fr, 1855)
        draw_caption(fr, caption_lines(CAP, font), font, 46)
        out = os.path.join(BASE, f"output/video/{name}.png")
        fr.save(out)
        print("saved", out)


if __name__ == "__main__":
    main()
