"""채널 배너(채널 아트)와 브랜딩 워터마크 생성.

유튜브 배너는 한 장을 만들어 기기마다 다르게 잘라 보여준다.
  - 전체 업로드 크기      2560 x 1440
  - 모든 기기 공통 안전영역 1546 x 423 (중앙)  ← 글자는 전부 여기 안에
  - 태블릿                1855 x 423
  - 데스크톱              2560 x 423
  - TV                    2560 x 1440 (전체가 보인다)

그래서 글자는 중앙 1546x423 안에만 두고, 바깥 날개에는 TV/데스크톱에서만
드러나는 배경 요소를 깐다. 잘려도 정보가 사라지지 않고, 안 잘리면 세계관이
넓어지는 구조.

색·질감은 영상과 같은 세계를 써야 하므로 archive_layout을 그대로 재사용한다.
실존 인물 얼굴은 쓸 수 없으므로(PRD 5항) 이름이 적히지 않은 빈 명패를 깐다 —
채널 포맷(마지막에 이름을 부른다) 그 자체를 배경으로 삼는 셈이다.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import archive_layout as A

W, H = 2560, 1440
SAFE_W, SAFE_H = 1546, 423          # 모든 기기에서 보이는 중앙 영역
TABLET_W = 1855

IVORY = (222, 213, 196)             # 아바타와 같은 값 — 작게 줄어도 살아남는 밝기
GOLD = (156, 124, 72)
DIM = (150, 141, 126)               # 부제 — 제목보다 한 단계 물러나게

KICKER = "독립운동가 한 사람의 마지막 이야기"
LINE = "이름을 부르다"
SUB = "우리가 부르지 않으면 사라지는 이름들 · 매일 한 편"


def _size(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1], box[0], box[1]


def _tracked(draw, xy, text, font, fill, track, anchor_center_x=None):
    """자간을 벌려 그린다. 작은 글씨는 자간이 있어야 '캡션'처럼 읽힌다."""
    widths = [_size(draw, ch, font)[0] for ch in text]
    total = sum(widths) + track * (len(text) - 1)
    x = (anchor_center_x - total / 2) if anchor_center_x is not None else xy[0]

    # 세로 기준은 문자열 전체의 잉크 상단 하나로 고정한다. 글자마다 제 bbox로
    # 맞추면 '·'처럼 키가 작은 글자가 윗선까지 끌려 올라가 위첨자처럼 보인다.
    oy = _size(draw, text, font)[3]
    for ch, w in zip(text, widths):
        draw.text((x - _size(draw, ch, font)[2], xy[1] - oy), ch, font=font, fill=fill)
        x += w + track
    return total


PLATE = (86, 78, 66)        # 명패 대지 — 배경(거의 검정) 위에서 겨우 떠 보이는 밝기


def _plate(w, h, seed):
    """이름이 적히지 않은 빈 명패 한 장 (이미지, 마스크).

    make_paper의 베이스는 거의 검정(PAPER)이라 밝기만 올리면 회색으로 뜬다.
    질감은 그대로 두고 색만 대지 톤으로 끌어올린다.
    """
    card = Image.blend(A.make_paper(w, h, seed=seed), Image.new("RGB", (w, h), PLATE), 0.78)

    d = ImageDraw.Draw(card)
    m = int(w * 0.08)                                   # 인화지 흰 여백
    win = [m, m, w - m, int(h * 0.60)]                  # 사진이 붙을 빈 창

    d.rectangle(win, fill=tuple(int(c * 0.38) for c in PLATE))
    d.rectangle(win, outline=tuple(int(c * 0.72) for c in PLATE), width=max(1, w // 150))

    # 이름이 들어갈 자리 — 비워둔 밑줄 두 개 (긴 줄=이름, 짧은 줄=생몰년)
    for ratio, y, col in ((0.56, 0.73, GOLD), (0.34, 0.85, A.MATTE)):
        ww = int(w * ratio)
        d.rectangle([(w - ww) / 2, h * y, (w + ww) / 2, h * y + max(2, h // 120)], fill=col)

    return card, A.torn_mask(w, h, amp=max(6, w // 40), seed=seed + 3)


def _wings(canvas, seed=13):
    """안전영역 바깥(TV·데스크톱에서만 보이는 곳)에 빈 명패를 흩어 놓는다.

    가운데로 갈수록 흐려지게 해서 제목을 방해하지 않게 한다.
    """
    layout = [
        # (중심 x, 중심 y, 폭, 높이, 회전, 불투명도)
        (250, 470, 320, 420, -4.5, 0.62),
        # 아래 두 장은 y를 내려 공통 안전영역(세로 508~931)을 비켜 간다.
        # 걸치면 모바일 크롭에서 명패 모서리가 제목 옆에 끼어 지저분해진다.
        (470, 1120, 250, 330, 3.0, 0.42),
        (110, 1090, 280, 360, 6.0, 0.34),
        (2310, 470, 320, 420, 4.0, 0.62),
        (2090, 1120, 250, 330, -3.0, 0.42),
        (2450, 1090, 280, 360, -6.0, 0.34),
        (1280, 168, 300, 250, 0.0, 0.20),      # 상단 중앙 — 아주 옅게만
        (1280, 1290, 300, 250, 0.0, 0.20),     # 하단 중앙 (TV에서만 보인다)
    ]
    for i, (cx, cy, pw, ph, rot, op) in enumerate(layout):
        card, mask = _plate(pw, ph, seed + i * 7)
        card = card.rotate(rot, Image.BICUBIC, expand=True)
        mask = mask.rotate(rot, Image.BICUBIC, expand=True)
        mask = mask.point(lambda p, o=op: int(p * o))
        mask = mask.filter(ImageFilter.GaussianBlur(1.2))
        canvas.paste(card, (int(cx - card.width / 2), int(cy - card.height / 2)), mask)
    return canvas


def build(out_path, sub=SUB, seed=7):
    canvas = A.make_paper(W, H, seed=seed)
    canvas = _wings(canvas)

    # 중앙 안전영역을 한 겹 어둡게 눌러 글자 대비를 확보한다
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse(
        [W / 2 - SAFE_W * 0.75, H / 2 - SAFE_H * 1.1,
         W / 2 + SAFE_W * 0.75, H / 2 + SAFE_H * 1.1], fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(150))
    canvas = Image.composite(ImageEnhance.Brightness(canvas).enhance(0.55), canvas, glow)

    draw = ImageDraw.Draw(canvas)
    cx = W / 2

    f_kick = A.load(A.NOTO_SERIF, 36, weight=400)
    f_main = A.load(A.NOTO_SERIF, 168, weight=700)
    f_sub = A.load(A.NOTO_SERIF, 40, weight=400)

    _, kh, _, _ = _size(draw, KICKER, f_kick)
    mw, mh, mox, moy = _size(draw, LINE, f_main)
    _, sh, _, _ = _size(draw, SUB, f_sub)

    gap_k = 40          # 키커 → 제목
    rule_gap = 34       # 제목 → 밑줄
    rule_h = 7
    gap_s = 38          # 밑줄 → 부제

    block = kh + gap_k + mh + rule_gap + rule_h + gap_s + sh
    if block > SAFE_H:
        raise SystemExit(f"안전영역 초과: {block}px > {SAFE_H}px")

    # 시각 중심을 기하 중심보다 살짝 위로
    y = (H - block) / 2 - 10

    _tracked(draw, (0, y), KICKER, f_kick, DIM, track=9, anchor_center_x=cx)
    y += kh + gap_k

    draw.text((cx - mw / 2 - mox, y - moy), LINE, font=f_main, fill=IVORY)
    y += mh + rule_gap

    rule_w = int(mw * 1.04)
    draw.rectangle([cx - rule_w / 2, y, cx + rule_w / 2, y + rule_h], fill=GOLD)
    y += rule_h + gap_s

    _tracked(draw, (0, y), sub, f_sub, DIM, track=4, anchor_center_x=cx)

    # 마지막에 필름 그레인 한 겹 — 요소들을 같은 층으로 묶어준다
    n = A._noise(W // 2, H // 2, 96, 160, seed + 5).resize((W, H), Image.BICUBIC)
    canvas = Image.blend(canvas, Image.merge("RGB", (n,) * 3), 0.055)

    canvas.save(out_path)
    return out_path


def preview_crops(src, out_path):
    """기기별 크롭을 한 장에 쌓아 잘림을 확인한다."""
    img = Image.open(src).convert("RGB")
    crops = []
    for label, (cw, ch) in (
        ("mobile/공통 1546x423", (SAFE_W, SAFE_H)),
        ("tablet 1855x423", (TABLET_W, SAFE_H)),
        ("desktop 2560x423", (W, SAFE_H)),
    ):
        box = ((W - cw) // 2, (H - ch) // 2, (W + cw) // 2, (H + ch) // 2)
        crops.append((label, img.crop(box)))

    # 모두 같은 폭으로 눕혀서 아래로 쌓는다 (맨 아래는 TV = 원본 전체)
    cw_out, pad = W // 2 - 20, 14
    rows = [c.resize((cw_out, int(c.height * cw_out / c.width)), Image.LANCZOS)
            for _, c in crops]
    rows.append(img.resize((cw_out, int(H * cw_out / W)), Image.LANCZOS))

    sheet = Image.new("RGB", (W // 2, sum(r.height for r in rows) + pad * (len(rows) + 1)),
                      (18, 17, 16))
    y = pad
    for r in rows:
        sheet.paste(r, (10, y))
        y += r.height + pad

    sheet.save(out_path)
    return out_path


def build_watermark(out_path, size=150):
    """동영상 우측 하단 브랜딩 워터마크(구독 버튼). 배경 투명.

    실제로는 영상 위에 아주 작게 얹히므로 글자 두 줄은 뭉갠다.
    빈 명패의 금색 밑줄 + '이름' 한 단어만 남기는 쪽이 판독된다.
    """
    S = size * 4                      # 4배로 그린 뒤 줄여서 계단을 없앤다
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    f = A.load(A.NOTO_SERIF, int(S * 0.30), weight=700)
    w, h, ox, oy = _size(d, "이름", f)
    y = (S - h - int(S * 0.14)) / 2
    d.text(((S - w) / 2 - ox, y - oy), "이름", font=f, fill=IVORY + (255,))

    ry = y + h + int(S * 0.09)
    rw = int(w * 1.10)
    d.rectangle([(S - rw) / 2, ry, (S + rw) / 2, ry + max(3, int(S * 0.028))],
                fill=GOLD + (255,))

    # 밝은 영상 위에서도 떨어져 보이도록 아주 옅은 그림자 한 겹
    shadow = img.split()[3].filter(ImageFilter.GaussianBlur(S * 0.022))
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    base.paste((0, 0, 0, 190), (0, 0), shadow.point(lambda p: min(255, int(p * 1.35))))
    out = Image.alpha_composite(base, img).resize((size, size), Image.LANCZOS)

    out.save(out_path)
    return out_path


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    assets = os.path.join(base, "assets")
    outdir = os.path.join(base, "output")
    os.makedirs(assets, exist_ok=True)
    os.makedirs(outdir, exist_ok=True)

    banner = build(os.path.join(assets, "channel_banner.png"))
    print("banner:", banner)
    print("preview:", preview_crops(banner, os.path.join(outdir, "channel_banner_preview.png")))
    print("watermark:", build_watermark(os.path.join(assets, "channel_watermark.png")))
