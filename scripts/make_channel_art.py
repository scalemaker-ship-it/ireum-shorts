"""채널 프로필 이미지 생성.

유튜브는 원형으로 잘라 보여주고 댓글창에서는 48px까지 작아진다.
그래서 요소는 최소로 두고, 글자를 크게 앉히는 쪽을 택했다.
실존 인물 얼굴은 쓸 수 없으므로(PRD 5항) 채널명 타이포가 곧 로고다.

영상과 같은 세계관으로 묶기 위해 배경·노후화·그레이딩은
archive_layout의 함수를 그대로 재사용한다.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import archive_layout as A

SIZE = 800
# 원형으로 잘리므로 내접 정사각(=SIZE/√2, 약 566) 안쪽에만 내용을 둔다
SAFE = int(SIZE / 1.414)

IVORY = (222, 213, 196)     # 본문보다 밝게 — 작게 줄었을 때 살아남아야 한다
GOLD = (156, 124, 72)       # 연도 스탬프 금색 계열, 한 톤 올림

LINE1 = "이름을"
LINE2 = "부르다"


def sepia(img):
    """archive_layout.grade()와 같은 색 세계를 쓰되 세월 효과는 뺀다.

    grade()는 내부에서 age_photo()를 호출해 스크래치·먼지를 얹는다. 영상 속
    실사진에는 맞지만 로고에 그으면 렌더링 오류처럼 보인다. 톤 매핑과
    비네팅만 그대로 가져오고 그 호출만 뺀 판본.
    """
    g = ImageEnhance.Contrast(img.convert("L")).enhance(1.04)
    P = A.PAPER
    out = Image.merge("RGB", (
        g.point(lambda p: int(P[0] + (p / 255) ** 1.68 * (146 - P[0]))),
        g.point(lambda p: int(P[1] + (p / 255) ** 1.74 * (131 - P[1]))),
        g.point(lambda p: int(P[2] + (p / 255) ** 1.86 * (106 - P[2]))),
    ))

    w, h = out.size
    vig = Image.new("L", (w, h), 0)
    ImageDraw.Draw(vig).ellipse([-w * 0.18, -h * 0.18, w * 1.18, h * 1.18], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(min(w, h) * 0.18))
    out = Image.composite(out, ImageEnhance.Brightness(out).enhance(0.62), vig)

    n = A._noise(w // 2, h // 2, 96, 160, 3).resize(out.size, Image.BICUBIC)
    return Image.blend(out, Image.merge("RGB", (n,) * 3), 0.07)


def _text_size(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1], box[0], box[1]


def build(out_path, seed=5):
    # age_photo는 쓰지 않는다 — 세로 스크래치가 글자를 가로질러 오류처럼 보인다.
    # 종이 질감과 비네팅만으로 충분하고, 로고는 판독성이 우선이다.
    canvas = A.make_paper(SIZE, SIZE, seed=seed)

    draw = ImageDraw.Draw(canvas)

    # 두 줄이 안전 영역 폭에 들어올 때까지 줄인다.
    # 48px까지 줄어드는 자리가 있으므로 본문(400)보다 훨씬 굵게 간다.
    size = 172
    while size > 90:
        f1 = A.load(A.NOTO_SERIF, size, weight=600)
        f2 = A.load(A.NOTO_SERIF, size, weight=800)
        w1 = _text_size(draw, LINE1, f1)[0]
        w2 = _text_size(draw, LINE2, f2)[0]
        if max(w1, w2) <= SAFE - 40:
            break
        size -= 6

    gap = int(size * 0.16)
    w1, h1, ox1, oy1 = _text_size(draw, LINE1, f1)
    w2, h2, ox2, oy2 = _text_size(draw, LINE2, f2)

    rule_gap = int(size * 0.20)      # 밑줄까지의 간격
    rule_h = max(5, size // 24)      # 얇으면 스크래치처럼 보인다 — 의도적으로 두껍게
    block_h = h1 + gap + h2 + rule_gap + rule_h
    # 시각 중심이 기하 중심보다 살짝 위에 있어야 안정적으로 보인다
    y = (SIZE - block_h) / 2 - size * 0.04

    draw.text(((SIZE - w1) / 2 - ox1, y - oy1), LINE1, font=f1, fill=IVORY)
    y += h1 + gap
    draw.text(((SIZE - w2) / 2 - ox2, y - oy2), LINE2, font=f2, fill=IVORY)
    y += h2 + rule_gap

    # 이름이 적힐 자리를 비워둔 명패의 밑줄 — 채널 포맷(이름을 마지막에 부른다) 그 자체
    rule_w = int(max(w1, w2) * 1.08)
    draw.rectangle(
        [(SIZE - rule_w) / 2, y, (SIZE + rule_w) / 2, y + rule_h],
        fill=GOLD,
    )

    canvas = sepia(canvas)
    canvas.save(out_path)
    return out_path


def preview_circle(src, out_path):
    """유튜브가 실제로 보여주는 원형 크롭 + 48px 축소 확인용."""
    img = Image.open(src).convert("RGB")
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, SIZE - 1, SIZE - 1], fill=255)

    bg = (24, 23, 21)
    sheet = Image.new("RGB", (SIZE + 360, SIZE), bg)
    sheet.paste(img, (0, 0), mask)

    # 실제로 노출되는 크기들을 세로로 쌓아 한눈에 비교한다
    y = 60
    for px in (240, 120, 48):
        small = img.resize((px, px), Image.LANCZOS)
        sheet.paste(small, (SIZE + 60, y), mask.resize((px, px), Image.LANCZOS))
        y += px + 40

    sheet.save(out_path)
    return out_path


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    assets = os.path.join(base, "assets")
    os.makedirs(assets, exist_ok=True)

    out = build(os.path.join(assets, "channel_avatar.png"))
    print("saved:", out)

    prev = preview_circle(out, os.path.join(base, "output", "channel_avatar_preview.png"))
    print("preview:", prev)
