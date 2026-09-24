"""아카이브(사진첩) 레이아웃 프레임 합성 — '이름을 부르다' 시리즈 전용.

잡학쿠키의 상하단 검은 바 레이아웃과 달리, 낡은 종이 질감 배경 위에
흰 여백 테두리를 두른 사진을 얹고 좌측 정렬 자막을 까는 구조.
"""
import os
import random

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

W, H = 1080, 1920

# 세이프 에어리어 — 숏츠 UI 대응
#
# **2026-09-13 실기기 측정값.** 그전까지는 전부 추정이었고 두 번 틀렸다.
#   150 — 잡학쿠키(상단 검은 바 레이아웃)에서 가져온 값. 이 레이아웃과 무관했다.
#    90 — "숏츠는 상단을 거의 안 가린다"는 내 추정. **틀렸다.**
# 비공개 업로드 후 스크린샷을 픽셀 단위로 재서 얻은 실제 값:
#   상태바(시계·배터리)      영상 y  -4 ~  34
#   **유튜브 아이콘 줄**      영상 y 109 ~ 151   (뒤로가기·검색·메뉴)
#   하단 채널명 줄            영상 y 1721 ~
# ⚠️ **측정한 기기(아이폰 13 프로맥스, 19.5:9)는 여유가 많은 쪽이다.**
# 화면비가 길수록 9:16 영상이 화면을 덜 채워 UI가 영상 좌표상 위에 머문다.
# 16:9에 가까운 기기(SE급)는 영상이 화면을 꽉 채워 같은 UI가 더 깊이 들어온다.
#   13 프로맥스(19.5:9) UI 하단 = 화면의 8.6% → 영상 y 151  (실측)
#   SE급(16:9)          UI 하단 = 화면의 9.6% → 영상 y ≈ 184 (추정)
# 210으로 잡았다가 사용자가 "아직 겹친다"고 해서 **250까지 내렸다.**
# SE급 추정치(184) 대비 80px 이상 여유다. 기기별 편차를 더는 추정하지 않고
# 넉넉히 두는 쪽을 택했다 — 상단이 잘리는 것보다 여백이 넓은 편이 낫다.
# 내릴 공간은 자막 기준선을 1380 → 1450으로 옮겨 확보했다(글자 크기는 46 유지).
TOP_SAFE = 250
# 숏츠 하단 UI(영상 제목 2줄 + 채널명 + 액션 버튼 + 진행바)는 생각보다 위로 올라온다.
# 320으로는 자막이 걸려서 430으로 올렸다.
BOTTOM_SAFE = 430
RIGHT_SAFE = 170           # 숏츠 우측 버튼 컬럼

PHOTO_BORDER = 26          # 사진 흰 여백 테두리 두께

# 사진 프레임 상단 y.
# 주의: 느린 줌으로 카드가 6% 커질 때 중심을 유지하므로 위로 약 17px 더 올라간다.
# 300으로 두면 줌 끝에서 상단이 283까지 올라와 연도 밑줄(306)을 파고든다.
# 2026-09-13: 370 → 480. 상단 UI를 피해 타이틀을 내린 만큼 같이 내렸다.
# live_card로 바뀌면서 카드 크기가 고정되어(사진 안에서만 카메라가 움직인다)
# 예전처럼 줌으로 카드가 20px 자라지 않는다. 카드 아래끝은 1072로 고정이다.
PHOTO_TOP = 480
# 연도 스탬프 y. **TOP_SAFE와 무관한 절대값**이다.
# 전에 TOP_SAFE + 78로 묶어 뒀다가, 상단 안전선을 바꾸자 연도까지 딸려 올라가
# 사진과 벌어졌다. 연도는 사진에 붙어 있어야 하므로 따로 고정한다.
YEAR_Y = 368

# 자막 블록의 아래 기준선.
# 2026-09-13: 1380 → 1450. 실기기 스크린샷을 재보니 **자막 네 줄 아래가 한참 비어 있었다**
# (자막 끝에서 채널명 줄까지 270px 이상). 상단 UI를 피해 전체를 내려야 했는데,
# 글자 크기를 줄이는 대신 여기를 내려서 공간을 만들었다. 사진 크기도 600 그대로 지킨다.
CAPTION_BOTTOM = 1450

_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "fonts")

GOTHIC = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
MYUNGJO = "/System/Library/Fonts/Supplemental/AppleMyungjo.ttf"
NOTO_SERIF = os.path.join(_FONT_DIR, "NotoSerifKR-var.ttf")      # 가변(200~900)
NANUM_BOLD = os.path.join(_FONT_DIR, "NanumMyeongjo-Bold.ttf")
NANUM_XBOLD = os.path.join(_FONT_DIR, "NanumMyeongjo-ExtraBold.ttf")


def load(path, size, index=0, weight=None):
    """폰트 로드. 가변 폰트면 weight 축을 지정할 수 있다."""
    f = ImageFont.truetype(path, size, index=index) if path.endswith(".ttc") \
        else ImageFont.truetype(path, size)
    if weight is not None:
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
    return f

PAPER = (9, 8, 7)          # 배경 베이스 — 거의 검정에 가까운 따뜻한 먹색
MATTE = (124, 114, 98)     # 사진 테두리 — 삭아서 어두워진 아이보리
INK = (178, 169, 153)      # 자막 본문 색
ACCENT = (132, 104, 60)    # 연도 스탬프 — 톤 다운된 빛바랜 금색
TITLE_COL = (118, 110, 97)  # 상단 채널명 — 매 프레임 떠 있으므로 눈에 안 띄게


def _noise(w, h, lo, hi, seed):
    rnd = random.Random(seed)
    n = Image.new("L", (w, h))
    n.putdata([rnd.randint(lo, hi) for _ in range(w * h)])
    return n


def make_paper(w, h, seed=7):
    """낡은 종이/천 질감. 균일 노이즈 대신 '큰 얼룩 + 미세 결' 2층으로 쌓는다."""
    base = Image.new("RGB", (w, h), PAPER)

    # 1층: 큰 얼룩 — 저해상 노이즈를 크게 뭉개서 유기적인 반점을 만든다
    blotch = _noise(w // 40, h // 40, 60, 200, seed) \
        .resize((w, h), Image.BICUBIC) \
        .filter(ImageFilter.GaussianBlur(60))
    paper = Image.blend(base, Image.merge("RGB", (blotch,) * 3), 0.10)

    # 2층: 미세한 종이 결 — 아주 옅게만
    fiber = _noise(w // 2, h // 2, 90, 165, seed + 1) \
        .resize((w, h), Image.BICUBIC) \
        .filter(ImageFilter.GaussianBlur(0.6))
    paper = Image.blend(paper, Image.merge("RGB", (fiber,) * 3), 0.035)

    # 가장자리를 어둡게 (기존과 반대 방향) — 시선을 사진으로 모은다
    vig = Image.new("L", (w, h), 0)
    ImageDraw.Draw(vig).ellipse([-w * 0.25, h * 0.02, w * 1.25, h * 0.98], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(260))
    return Image.composite(paper, ImageEnhance.Brightness(paper).enhance(0.45), vig)


def _torn_profile(n, rnd):
    """찢긴 가장자리용 요철. 완만한 물결(저주파) 위에 잘게 떨리는 결(고주파)을 얹는다.

    실제 찢긴 종이는 진폭이 크지 않고 대신 촘촘하게 떨린다. 큰 진폭으로
    지그재그를 만들면 톱니처럼 보여 오히려 가짜 티가 난다.
    """
    coarse = [rnd.random() for _ in range(max(4, n // 12) + 1)]
    out = []
    for i in range(n):
        t = i / max(1, n - 1) * (len(coarse) - 1)
        a, b = int(t), min(int(t) + 1, len(coarse) - 1)
        base = coarse[a] + (coarse[b] - coarse[a]) * (t - a)   # 저주파 물결
        out.append(0.32 + base * 0.34 + rnd.random() * 0.34)   # 고주파 결
    return out


def torn_mask(w, h, amp=11, seed=5):
    """네 변을 불규칙하게 뜯어낸 알파 마스크."""
    rnd = random.Random(seed)
    sx, sy = max(90, w // 4), max(90, h // 4)   # 촘촘하게 샘플링 = 고주파 결
    top, right = _torn_profile(sx + 1, rnd), _torn_profile(sy + 1, rnd)
    bottom, left = _torn_profile(sx + 1, rnd), _torn_profile(sy + 1, rnd)

    pts = [(w * i / sx, amp * top[i]) for i in range(sx + 1)]
    pts += [(w - amp * right[i], h * i / sy) for i in range(sy + 1)]
    pts += [(w * i / sx, h - amp * bottom[i]) for i in range(sx, -1, -1)]
    pts += [(amp * left[i], h * i / sy) for i in range(sy, -1, -1)]

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(0.5))


def age_photo(img, seed=11):
    """오래된 인화지 흉내 — 폭싱 반점, 먼지·스크래치, 가장자리 변색, 디테일 손실."""
    rnd = random.Random(seed)
    w, h = img.size
    out = img.copy()

    # 0) 색이 바래며 대비가 주저앉는다
    out = ImageEnhance.Contrast(out).enhance(0.88)

    # 1) 폭싱(foxing) — 아주 작은 반점이 불균일하게 '군집'한다.
    #    큰 원을 흩뿌리면 브러시 자국처럼 보여 가짜 티가 나므로 클러스터로 찍는다.
    fox = Image.new("L", (w, h), 0)
    fd = ImageDraw.Draw(fox)
    for _ in range(rnd.randint(5, 9)):
        cx, cy = rnd.randrange(w), rnd.randrange(h)
        spread = rnd.uniform(w * 0.04, w * 0.13)
        for _ in range(rnd.randint(6, 22)):
            x = int(rnd.gauss(cx, spread))
            y = int(rnd.gauss(cy, spread))
            r = rnd.randint(1, 4)
            fd.ellipse([x - r, y - r, x + r, y + r], fill=rnd.randint(30, 80))
    fox = fox.filter(ImageFilter.GaussianBlur(2.4))
    out.paste(Image.new("RGB", (w, h), (104, 76, 42)), (0, 0), fox)

    # 2) 얼룩진 노출 — 오래된 인화지는 밝기가 고르지 않다
    patch = _noise(max(2, w // 70), max(2, h // 70), 80, 190, seed + 5) \
        .resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(w * 0.07))
    out = Image.composite(out, ImageEnhance.Brightness(out).enhance(0.8), patch)

    # 3) 가장자리 변색 — 테두리 쪽이 더 누렇게 삭는다 (넓고 부드럽게)
    edge = Image.new("L", (w, h), 255)
    ImageDraw.Draw(edge).rectangle(
        [w * 0.04, h * 0.04, w * 0.96, h * 0.96], fill=0)
    edge = edge.filter(ImageFilter.GaussianBlur(min(w, h) * 0.09))
    edge = edge.point(lambda p: int(p * 0.5))
    out.paste(Image.new("RGB", (w, h), (112, 84, 48)), (0, 0), edge)

    # 4) 먼지와 스크래치 — 별도 레이어에 그린 뒤 옅게 섞어 인위적인 티를 줄인다
    marks = out.copy()
    md = ImageDraw.Draw(marks)
    for _ in range(max(14, w * h // 14000)):
        x, y = rnd.randrange(w), rnd.randrange(h)
        tone = rnd.choice([(224, 214, 194), (230, 222, 204), (46, 38, 30)])
        md.ellipse([x, y, x + 1, y + 1], fill=tone)
    for _ in range(rnd.randint(2, 4)):
        x, y0 = rnd.randrange(w), rnd.randrange(h)
        md.line([(x, y0), (x + rnd.randint(-5, 5), y0 + rnd.randint(25, 110))],
                fill=(206, 196, 176), width=1)
    marks = marks.filter(ImageFilter.GaussianBlur(0.4))
    out = Image.blend(out, marks, 0.55)

    # 5) 디테일 손실 — 오래된 인화는 선예도가 떨어진다
    return out.filter(ImageFilter.GaussianBlur(0.5))


def grade(img):
    """세피아 그레이딩. 암부를 배경 먹색까지 끌어내려 사진이 배경에 스며들게 한다."""
    g = ImageEnhance.Contrast(img.convert("L")).enhance(1.04)

    # 흰 끝을 낮추고(전체 어둡게), 검은 끝은 배경색과 일치시킨다
    sepia = Image.merge("RGB", (
        g.point(lambda p: int(PAPER[0] + (p / 255) ** 1.68 * (146 - PAPER[0]))),
        g.point(lambda p: int(PAPER[1] + (p / 255) ** 1.74 * (131 - PAPER[1]))),
        g.point(lambda p: int(PAPER[2] + (p / 255) ** 1.86 * (106 - PAPER[2]))),
    ))

    # 사진 자체의 가장자리 비네팅 — 프레임 안쪽부터 배경 쪽으로 녹아든다
    pw, ph = sepia.size
    vig = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(vig).ellipse([-pw * 0.18, -ph * 0.18, pw * 1.18, ph * 1.18], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(min(pw, ph) * 0.18))
    sepia = Image.composite(sepia, ImageEnhance.Brightness(sepia).enhance(0.62), vig)

    sepia = age_photo(sepia)

    n = _noise(pw // 2, ph // 2, 96, 160, 3).resize(sepia.size, Image.BICUBIC)
    return Image.blend(sepia, Image.merge("RGB", (n,) * 3), 0.07)


def bleed(canvas, photo, x, y, spread=200, strength=0.5):
    """사진 색이 배경으로 번지는 광량 누출. 사진과 배경을 잇는 핵심 장치."""
    w, h = photo.size
    glow = photo.resize((max(1, w // 14), max(1, h // 14)), Image.LANCZOS) \
                .resize((w + spread * 2, h + spread * 2), Image.BICUBIC) \
                .filter(ImageFilter.GaussianBlur(spread * 0.45))
    glow = ImageEnhance.Brightness(glow).enhance(0.7)

    mask = Image.new("L", glow.size, 0)
    ImageDraw.Draw(mask).rectangle(
        [spread // 2, spread // 2, glow.width - spread // 2, glow.height - spread // 2],
        fill=int(255 * strength))
    mask = mask.filter(ImageFilter.GaussianBlur(spread * 0.5))
    canvas.paste(glow, (x - spread, y - spread), mask)


# 세로 사진 높이 상한. 사진 아래 이름표(2줄)와 자막(최대 5줄)이 들어가야 하고
# 느린 줌으로 6%까지 커지므로 그만큼 여유를 두고 잡는다.
MAX_PHOTO_H = 600


def fit_photo(photo, box_w, max_h=None):
    """사진을 프레임에 맞춘다. 원본 비율 유지(크롭 없음).

    세로로 긴 사진은 너비에 맞추면 자막 자리를 잠식하므로 높이 기준으로 맞춘다.
    """
    max_h = MAX_PHOTO_H if max_h is None else max_h   # 기본값을 호출 시점에 읽는다
    ratio = box_w / photo.width
    if photo.height * ratio > max_h:
        ratio = max_h / photo.height
    return photo.resize((max(1, int(photo.width * ratio)),
                         max(1, int(photo.height * ratio))), Image.LANCZOS)


NO_LEAD = ".,!?\"')」』"   # 줄 첫머리에 오면 안 되는 문장부호


def _clauses(text):
    """구두점 뒤에서 끊어 절 단위로 나눈다 (구두점은 앞 절에 붙인다)."""
    out, cur = [], ""
    for ch in text:
        cur += ch
        if ch in ".,?!":
            out.append(cur.strip())
            cur = ""
    if cur.strip():
        out.append(cur.strip())
    return out


def wrap(draw, text, font, max_w):
    """절 단위 줄바꿈.

    구두점 뒤 몇 글자만 걸치고 줄이 바뀌는 걸 막기 위해, 절이 통째로 안 들어가면
    구두점에서 미리 끊는다. 절 하나가 한 줄을 넘을 때만 어절 단위로 쪼갠다.
    """
    lines, cur = [], ""

    def flush():
        nonlocal cur
        if cur:
            lines.append(cur)
            cur = ""

    for clause in _clauses(text):
        if draw.textlength(f"{cur} {clause}".strip(), font=font) <= max_w:
            cur = f"{cur} {clause}".strip()
            continue

        flush()
        if draw.textlength(clause, font=font) <= max_w:
            cur = clause
            continue

        for word in clause.split(" "):          # 절 자체가 길면 어절 단위로
            trial = f"{cur} {word}".strip()
            if cur and draw.textlength(trial, font=font) > max_w:
                flush()
                cur = word
            else:
                cur = trial
    flush()

    # 다음 줄이 문장부호로 시작하면 앞 줄 끝에 붙인다
    merged = []
    for line in lines:
        if merged and line and line[0] in NO_LEAD:
            head = line[0]
            merged[-1] += head
            line = line[1:].strip()
            if not line:
                continue
        merged.append(line)
    return merged


def build_card(photo_path, seed=5):
    """찢긴 인화지 한 장을 만든다. -> (카드 이미지, 알파 마스크, 그레이딩된 사진)"""
    photo = grade(Image.open(photo_path).convert("RGB"))
    photo = fit_photo(photo, (W - 150 * 2) - PHOTO_BORDER * 2)

    fw, fh = photo.width + PHOTO_BORDER * 2, photo.height + PHOTO_BORDER * 2

    card = Image.new("RGB", (fw, fh), MATTE)
    # 테두리도 균일하지 않게 얼룩지운다
    stain = _noise(max(2, fw // 30), max(2, fh // 30), 70, 190, 21) \
        .resize((fw, fh), Image.BICUBIC).filter(ImageFilter.GaussianBlur(28))
    card = Image.composite(card, ImageEnhance.Brightness(card).enhance(0.8), stain)
    card.paste(photo, (PHOTO_BORDER, PHOTO_BORDER))

    mask = torn_mask(fw, fh, amp=11, seed=seed)

    # 뜯긴 단면에 드러나는 종이 속살 — 얇게 한 겹만
    fringe = ImageChops.subtract(mask, mask.filter(ImageFilter.MinFilter(3)))
    fringe = fringe.point(lambda p: int(p * 0.55))
    card.paste(Image.new("RGB", (fw, fh), (186, 175, 154)), (0, 0), fringe)
    return card, mask, photo


def card_pos(card):
    return (W - card.width) // 2, PHOTO_TOP


def paste_card(canvas, card, mask, photo=None, pos=None, shadow=True):
    """카드를 배경 위에 올린다 (광량 누출 -> 그림자 -> 카드 순)."""
    x, y = pos if pos else card_pos(card)
    if photo is not None:
        bleed(canvas, photo, x + PHOTO_BORDER, y + PHOTO_BORDER)
    if shadow:
        sh = Image.new("L", (card.width + 80, card.height + 80), 0)
        sh.paste(mask, (40, 46))
        sh = sh.filter(ImageFilter.GaussianBlur(24)).point(lambda p: int(p * 0.78))
        canvas.paste(Image.new("RGB", sh.size, (0, 0, 0)), (x - 40, y - 40), sh)
    canvas.paste(card, (x, y), mask)
    return canvas


TITLE_SIZE = 54          # 상단 소제목 크기 (2026-09-11 확정)

# 38px 기준으로 실측한 세로 리듬. 타이틀이 커지면 이 간격들도 같은 비율로 벌어진다.
_BASE_TITLE = 38
_TITLE_H38 = 49          # 38px 소제목 글자 높이(bbox)
TITLE_Y = TOP_SAFE       # 소제목은 상단 안전선에 붙여 앉힌다


def set_title_size(size):
    """소제목 크기를 바꾼다. **연도와 사진은 건드리지 않는다.**

    글자 크기와 무관하게 소제목은 상단 안전선(TOP_SAFE)에 붙어 있고,
    양옆 가는 선만 크기에 반비례해 짧아진다.
    """
    global TITLE_SIZE, TITLE_Y
    TITLE_SIZE = size
    # 소제목은 항상 상단 안전선에 붙인다. 연도·사진과의 간격은 그 아래에서
    # 자연히 벌어진다(54px·사진 370 기준 98px).
    TITLE_Y = TOP_SAFE
    return TITLE_Y


def draw_title(canvas, text, size=None):
    """상단 소제목. 매 프레임 떠 있으므로 자막과 경쟁하지 않게 어둡게.

    크기를 키울 때는 아래 두 가지가 걸린다.
    - 세로: 글자 아래가 연도 스탬프(YEAR_Y)를 침범한다
    - 가로: 양옆 가는 선이 안전영역(RIGHT_SAFE) 밖으로 나간다 → 선을 줄이거나 뺀다
    """
    size = size or TITLE_SIZE
    draw = ImageDraw.Draw(canvas)
    f = load(NOTO_SERIF, size, weight=500)
    w = draw.textlength(text, font=f)
    x, y = (W - w) / 2, TITLE_Y
    draw.text((x, y), text, font=f, fill=TITLE_COL)

    # 좌우로 뻗는 가는 선 (표제 느낌).
    # 글자가 커질수록 **선은 짧아진다.** 같이 길어지면 상단이 선으로 꽉 차 보이고,
    # 글자가 이미 충분히 무거워서 선이 거들 필요가 없다.
    ly = y + int(size * 0.66)                     # 글자의 세로 중앙에 걸친다
    gap = int(30 * (size / _BASE_TITLE) ** 0.5)
    # 반비례를 1.5제곱으로 걸어 **크기가 커질수록 더 빠르게 짧아지게** 한다.
    # 글자가 무거워지면 선은 장식이 아니라 작은 티크(tick)로 물러나야 균형이 맞다.
    ln = int(100 * (_BASE_TITLE / size) ** 1.5)
    left, right = x - gap - ln, x + w + gap + ln
    if left >= 60 and right <= W - 60:            # 양옆이 남을 때만 선을 그린다
        for x0, x1 in ((left, x - gap), (x + w + gap, right)):
            draw.line([(x0, ly), (x1, ly)], fill=TITLE_COL, width=1)
    return canvas


def draw_year(canvas, year):
    draw = ImageDraw.Draw(canvas)
    f = load(NOTO_SERIF, 44, weight=500)
    y = YEAR_Y                                    # 타이틀 아래, 사진 위
    draw.text((150, y), str(year), font=f, fill=ACCENT)
    ly = y + 64
    draw.line([(152, ly), (152 + draw.textlength(str(year), font=f), ly)],
              fill=ACCENT, width=2)
    return canvas


def draw_nameplate(canvas, card, pos, name, dates, alpha=1.0):
    """인화지 바로 아래에 이름과 생몰년을 적는다 (박물관 명패처럼)."""
    if alpha <= 0.01:
        return canvas
    layer = canvas.copy()
    draw = ImageDraw.Draw(layer)
    cx = pos[0] + card.width / 2
    y = pos[1] + card.height + 30

    f_name = load(NOTO_SERIF, 46, weight=500)
    f_date = load(NOTO_SERIF, 30, weight=400)
    for text, font, dy, fill in ((name, f_name, 0, INK),
                                 (f"({dates})", f_date, 60, ACCENT)):
        w = draw.textlength(text, font=font)
        draw.text((cx - w / 2, y + dy), text, font=font, fill=fill)
    return Image.blend(canvas, layer, alpha)


def draw_credit(canvas, card, pos, lines, alpha=1.0):
    """이름표 아래 출처 표기. 마지막 추모 컷에만 넣는다.

    60초 제한 때문에 별도 출처 카드를 둘 여유가 없어, 초상이 떠 있는 화면의
    이름표와 자막 사이 빈 공간을 쓴다. 본문을 방해하지 않게 아주 작고 어둡게.
    """
    if alpha <= 0.01:
        return canvas
    layer = canvas.copy()
    draw = ImageDraw.Draw(layer)
    f = load(NOTO_SERIF, 24, weight=400)
    cx = pos[0] + card.width / 2
    y = pos[1] + card.height + 128          # 이름표(2줄) 아래
    for i, text in enumerate(lines):
        w = draw.textlength(text, font=f)
        draw.text((cx - w / 2, y + i * 32), text, font=f, fill=TITLE_COL)
    return Image.blend(canvas, layer, alpha)


def caption_lines(text, font):
    d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    return wrap(d, text, font, W - 150 - RIGHT_SAFE)


# 자막 블록이 넘어서면 안 되는 위쪽 경계.
# 인화지 카드는 PHOTO_TOP(480) + 테두리(26*2) + 사진 최대 높이(600) = 1132까지 내려온다.
# live_card는 카드 크기를 바꾸지 않으므로 여기서 더 자라지 않는다.
CAPTION_TOP = 1190


def fit_caption(text, base_size=46, weight=400, min_size=36):
    """자막이 사진을 침범하지 않도록 글자 크기를 줄여 맞춘다.

    긴 인용문이 들어오면 줄 수가 늘고, 자막은 아래(CAPTION_BOTTOM)를 기준으로
    위로 자라므로 사진 카드를 덮어버린다. 1화 08_quote(유언)가 7줄이 되면서
    실제로 사진 위에 글자가 겹쳐 찍혔다. 회차마다 사람이 눈으로 확인할 수 없으니
    여기서 자동으로 막는다.
    """
    size = base_size
    while True:
        font = load(NOTO_SERIF, size, weight=weight)
        lines = caption_lines(text, font)
        top = CAPTION_BOTTOM - int(size * 1.42) * len(lines)
        if top >= CAPTION_TOP or size <= min_size:
            return lines, font, size
        size -= 2


def max_caption_lines(size):
    """사진을 침범하지 않고 들어갈 수 있는 자막 줄 수."""
    return max(1, (CAPTION_BOTTOM - CAPTION_TOP) // int(size * 1.42))


def paginate(lines, size):
    """긴 자막을 여러 장으로 나눈다.

    넘치면 글자를 줄이는 방법도 있지만 그러면 컷마다 자막 크기가 달라져 보인다.
    **책장 넘기듯 다음 장으로 넘기는 편이 낫다.** 마지막 장에 한 줄만 남는 걸
    막으려고 장수를 먼저 정하고 고르게 나눈다(5줄 → 4+1이 아니라 3+2).
    """
    mx = max_caption_lines(size)
    if len(lines) <= mx:
        return [lines]
    pages = -(-len(lines) // mx)                  # 올림
    per = -(-len(lines) // pages)                 # 고르게 분배
    return [lines[i:i + per] for i in range(0, len(lines), per)]


def caption_pages(text, size=46, weight=400):
    """텍스트를 줄바꿈하고 장 단위로 나눠 돌려준다. 장별 글자 수도 함께."""
    font = load(NOTO_SERIF, size, weight=weight)
    pages = paginate(caption_lines(text, font), size)
    counts = [len("".join(p)) for p in pages]
    top = CAPTION_BOTTOM - int(size * 1.42) * max(len(p) for p in pages)
    return pages, counts, font, top


def page_at(counts, reveal):
    """지금까지 찍힌 글자 수(reveal)가 몇 번째 장의 어디인지."""
    cum = 0
    for i, c in enumerate(counts):
        if reveal <= cum + c or i == len(counts) - 1:
            return i, reveal - cum
        cum += c
    return 0, reveal


def draw_caption(canvas, lines, font, size, reveal=None, cursor=False, top=None):
    """자막을 그린다. reveal이 주어지면 그 글자 수까지만 (타이핑 연출).

    top을 주면 그 y에서 시작한다. 여러 장으로 나뉜 자막은 장마다 줄 수가 달라
    아래 기준으로 앉히면 블록이 위아래로 튄다. 장 전환에는 고정 top을 쓴다.
    """
    draw = ImageDraw.Draw(canvas)
    line_h = int(size * 1.42)
    cy = top if top is not None else CAPTION_BOTTOM - line_h * len(lines)

    left = len(''.join(lines)) if reveal is None else reveal
    for line in lines:
        if left <= 0:
            break
        shown = line if left >= len(line) else line[:left]
        draw.text((150, cy), shown, font=font, fill=INK)
        if cursor and left < len(line):
            cx = 150 + draw.textlength(shown, font=font) + 6
            draw.line([(cx, cy + size * 0.18), (cx, cy + size * 1.02)], fill=INK, width=3)
        left -= len(line)
        cy += line_h
    return canvas


def compose(photo_path, caption, year, out_path, caption_font=NOTO_SERIF,
            caption_size=46, caption_weight=400):
    canvas = make_paper(W, H)
    card, mask, photo = build_card(photo_path)
    paste_card(canvas, card, mask, photo)
    draw_year(canvas, year)

    f_cap = load(caption_font, caption_size, index=1, weight=caption_weight)
    draw_caption(canvas, caption_lines(caption, f_cap), f_cap, caption_size)

    canvas.save(out_path)
    print(f"saved {out_path}  ({W}x{H})")


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(__file__), "..")
    photo = os.path.join(base, "output/images/kang_01_station.png")
    caption = "1919년 9월 2일 오후 다섯 시. 경성 남대문역에 폭탄이 터졌다."

    # Noto Serif KR — 굵기 비교
    for w in (400, 450, 500):
        compose(photo, caption, 1919,
                os.path.join(base, f"output/video/weight_{w}.png"),
                caption_font=NOTO_SERIF, caption_size=46, caption_weight=w)
