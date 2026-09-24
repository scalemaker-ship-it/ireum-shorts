"""사진 '안'이 움직이는 인화지 카드.

기존 방식은 인화지 전체가 통째로 커졌다 — 사진이 부푸는 것이지 카메라가 움직이는
게 아니다. 여기서는 **인화지 틀은 고정한 채 사진 안에서 창을 잘라 이동**한다.
카메라가 장면을 훑는 느낌이 나고, 넓은 구도일수록 차이가 크다.

노후화 처리 순서가 중요하다.
- **세피아 그레이딩은 원본 전체에 먼저** 건다. 창이 움직여도 톤이 일정해야 한다.
- **폭싱·스크래치·비네팅은 잘라낸 뒤 카드 크기에서** 건다. 이건 인화지에 난 흠이라
  장면이 아니라 **종이에 붙어 있어야** 한다. 원본에 먼저 걸면 얼룩이 사진과 같이
  흘러가서 '유리창 너머 먼지'처럼 보인다.
"""
import math
import os
import random
import sys

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import archive_layout as A  # noqa: E402
from archive_layout import (MATTE, PHOTO_BORDER, W, _noise, age_photo,  # noqa: E402
                            fit_photo, torn_mask)

ZOOM_RANGE = 0.12      # 창 크기 변화폭 (기존 카드 확대 6%보다 크게 잡아도 된다)
DRIFT = 0.05           # 창 중심이 이동하는 폭 (사진 크기 대비)


def _sepia_only(img):
    """age_photo 없이 톤만. archive_layout.grade에서 노후화를 뺀 버전."""
    g = ImageEnhance.Contrast(img.convert("L")).enhance(1.04)
    P = A.PAPER
    return Image.merge("RGB", (
        g.point(lambda p: int(P[0] + (p / 255) ** 1.68 * (146 - P[0]))),
        g.point(lambda p: int(P[1] + (p / 255) ** 1.74 * (131 - P[1]))),
        g.point(lambda p: int(P[2] + (p / 255) ** 1.86 * (106 - P[2]))),
    ))


def _wear(size, seed=11):
    """인화지에 난 흠을 **한 번만** 만들어 둔다 (폭싱·얼룩·먼지·스크래치·비네팅).

    ⚠️ 이걸 프레임마다 계산하면 안 된다. 흠집은 종이에 고정된 것이라 매번 같은데,
    `age_photo`는 호출마다 전체 크기 복사본을 여러 장 만든다. 프레임마다 부르니
    렌더 중 시스템 메모리가 97MB까지 떨어져 프로세스가 죽었다.
    마스크만 미리 만들어 두고 프레임에서는 값싼 합성만 한다.
    """
    w, h = size
    rnd = random.Random(seed)

    fox = Image.new("L", (w, h), 0)
    fd = ImageDraw.Draw(fox)
    for _ in range(rnd.randint(5, 9)):
        cx, cy = rnd.randrange(w), rnd.randrange(h)
        spread = rnd.uniform(w * 0.04, w * 0.13)
        for _ in range(rnd.randint(6, 22)):
            x, y = int(rnd.gauss(cx, spread)), int(rnd.gauss(cy, spread))
            r = rnd.randint(1, 4)
            fd.ellipse([x - r, y - r, x + r, y + r], fill=rnd.randint(30, 80))
    fox = fox.filter(ImageFilter.GaussianBlur(2.4))

    patch = _noise(max(2, w // 70), max(2, h // 70), 80, 190, seed + 5) \
        .resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(w * 0.07))

    edge = Image.new("L", (w, h), 255)
    ImageDraw.Draw(edge).rectangle([w * .04, h * .04, w * .96, h * .96], fill=0)
    edge = edge.filter(ImageFilter.GaussianBlur(min(w, h) * 0.09)).point(lambda p: int(p * .5))

    marks = Image.new("L", (w, h), 0)          # 먼지·스크래치 (알파로만 얹는다)
    md = ImageDraw.Draw(marks)
    for _ in range(max(14, w * h // 14000)):
        x, y = rnd.randrange(w), rnd.randrange(h)
        md.ellipse([x, y, x + 1, y + 1], fill=rnd.randint(90, 150))
    for _ in range(rnd.randint(2, 4)):
        x, y0 = rnd.randrange(w), rnd.randrange(h)
        md.line([(x, y0), (x + rnd.randint(-5, 5), y0 + rnd.randint(25, 110))],
                fill=110, width=1)
    marks = marks.filter(ImageFilter.GaussianBlur(0.4))

    vig = Image.new("L", (w, h), 0)
    ImageDraw.Draw(vig).ellipse([-w * .18, -h * .18, w * 1.18, h * 1.18], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(min(w, h) * 0.18))

    grain = _noise(w // 2, h // 2, 96, 160, 3).resize((w, h), Image.BICUBIC)
    return {"fox": fox, "patch": patch, "edge": edge, "marks": marks,
            "vig": vig, "grain": grain,
            "c_fox": Image.new("RGB", (w, h), (104, 76, 42)),
            "c_edge": Image.new("RGB", (w, h), (112, 84, 48)),
            "c_mark": Image.new("RGB", (w, h), (224, 214, 194)),
            "grain_rgb": None}


def _apply_wear(view, wr):
    """미리 만든 흠을 값싼 합성으로 얹는다."""
    out = ImageEnhance.Contrast(view).enhance(0.88)
    out = Image.composite(out, ImageEnhance.Brightness(out).enhance(0.62), wr["vig"])
    out.paste(wr["c_fox"], (0, 0), wr["fox"])
    out = Image.composite(out, ImageEnhance.Brightness(out).enhance(0.8), wr["patch"])
    out.paste(wr["c_edge"], (0, 0), wr["edge"])
    out.paste(wr["c_mark"], (0, 0), wr["marks"])
    out = out.filter(ImageFilter.GaussianBlur(0.5))
    if wr["grain_rgb"] is None:
        wr["grain_rgb"] = Image.merge("RGB", (wr["grain"],) * 3)
    return Image.blend(out, wr["grain_rgb"], 0.07)


def prepare(photo_path, seed=5, max_h=None):
    """카드 틀과 원본 사진을 한 번만 만들어 둔다.

    max_h를 주면 사진 높이를 그만큼으로 제한한다. 이름표·출처가 붙는 추모 컷에서
    그 블록이 자막을 밀지 않도록 호출부가 계산해 넘긴다.
    """
    src = _sepia_only(Image.open(photo_path).convert("RGB"))
    box = fit_photo(Image.open(photo_path).convert("RGB"),
                    (W - 150 * 2) - PHOTO_BORDER * 2, max_h=max_h).size
    fw, fh = box[0] + PHOTO_BORDER * 2, box[1] + PHOTO_BORDER * 2

    frame = Image.new("RGB", (fw, fh), MATTE)
    stain = _noise(max(2, fw // 30), max(2, fh // 30), 70, 190, 21) \
        .resize((fw, fh), Image.BICUBIC).filter(ImageFilter.GaussianBlur(28))
    frame = Image.composite(frame, ImageEnhance.Brightness(frame).enhance(0.8), stain)

    mask = torn_mask(fw, fh, amp=11, seed=seed)
    fringe = ImageChops.subtract(mask, mask.filter(ImageFilter.MinFilter(3)))
    fringe = fringe.point(lambda p: int(p * 0.55))
    frame.paste(Image.new("RGB", (fw, fh), (186, 175, 154)), (0, 0), fringe)

    rnd = random.Random(seed)
    plan = {
        "zoom_in": rnd.random() < 0.5,
        "dir": rnd.choice([(1, 0), (-1, 0), (0.7, 0.7), (-0.7, 0.7), (0.7, -0.7)]),
    }
    return {"src": src, "box": box, "frame": frame, "mask": mask, "plan": plan,
            "wear": _wear(box, seed=11)}


def _window(src, box, t, plan):
    """진행도 t에서 잘라낼 창. 원본 밖으로 나가지 않게 붙잡는다."""
    sw, sh = src.size
    ar = box[0] / box[1]
    # 사진에 꽉 차는 최대 창
    if sw / sh > ar:
        base_h, base_w = sh, sh * ar
    else:
        base_w, base_h = sw, sw / ar

    s = 1 - ZOOM_RANGE * (t if plan["zoom_in"] else (1 - t))
    cw, ch = base_w * s, base_h * s

    dx, dy = plan["dir"]
    mx, my = (sw - cw) / 2, (sh - ch) / 2          # 중심에서 움직일 수 있는 최대치
    ox = dx * min(mx, sw * DRIFT) * (t - 0.5) * 2
    oy = dy * min(my, sh * DRIFT) * (t - 0.5) * 2
    cx, cy = sw / 2 + ox, sh / 2 + oy
    x0 = max(0, min(sw - cw, cx - cw / 2))
    y0 = max(0, min(sh - ch, cy - ch / 2))
    return (int(x0), int(y0), int(x0 + cw), int(y0 + ch))


def frame_at(prep, t, fx=None, fi=0):
    """진행도 t의 카드 한 장. fx는 장면별 움직임(smoke/flicker/snow)."""
    view = prep["src"].crop(_window(prep["src"], prep["box"], t, prep["plan"]))
    view = view.resize(prep["box"], Image.LANCZOS)

    if fx:
        view = fx(view, t, fi)

    # 비네팅과 노후화는 **잘라낸 뒤** 건다 — 흠집은 장면이 아니라 인화지에 붙어 있어야 한다
    view = _apply_wear(view, prep["wear"])

    card = prep["frame"].copy()
    card.paste(view, (PHOTO_BORDER, PHOTO_BORDER))
    return card, prep["mask"], view


# ---------- 장면별 움직임 ----------

_WISP = None


def _wisp_tile():
    """연기 결. **밝은 부분만 남겨** 뭉게뭉게한 가닥을 만든다.

    처음엔 부드러운 노이즈를 그대로 섞었는데, 어두운 세피아 화면 위에서는
    전체가 조금 밝아질 뿐 아무것도 안 보였다. 연기는 균일한 안개가 아니라
    **빛을 머금은 가닥**이라 상위 밝기만 남기고 알파로 얹어야 보인다.
    """
    global _WISP
    if _WISP is None:
        # ⚠️ 블러 뒤에는 **반드시 다시 펴야 한다(autocontrast).**
        # 난수를 세게 블러하면 값이 전부 중간값 근처로 평탄해진다. 그 상태에서
        # '상위 밝기만 남겨라'를 걸면 아무것도 남지 않아 레이어가 통째로 투명해진다.
        # 실제로 그렇게 만들어 두 번이나 '연기가 안 보인다'는 지적을 받았다.
        n = _noise(180, 120, 0, 255, 77).filter(ImageFilter.GaussianBlur(5))
        n = ImageOps.autocontrast(n)
        _WISP = n.point(lambda v: 0 if v < 118 else min(255, int((v - 118) * 2.1)))
        _WISP = ImageOps.autocontrast(_WISP.filter(ImageFilter.GaussianBlur(4)))
    return _WISP


def smoke(strength=0.5, speed=140, rise=18, tone=(206, 194, 170)):
    """연기가 옆으로 흐르며 천천히 떠오른다. 폭발 현장, 새벽 강."""
    def f(img, t, fi):
        w, h = img.size
        tile = _wisp_tile().resize((w * 2, int(h * 1.3)), Image.BICUBIC)
        ox = int((t * speed) % w)
        oy = int(tile.height - h - t * rise) % max(1, tile.height - h)
        band = tile.crop((ox, oy, ox + w, oy + h))
        band = band.point(lambda v: int(v * strength))
        out = img.copy()
        out.paste(Image.new("RGB", (w, h), tone), (0, 0), band)
        return out
    return f


def flicker(amp=0.07, hz=0.7):
    """등불·창빛이 천천히 흔들린다. 감옥, 방 안, 밤 장면."""
    def f(img, t, fi):
        k = 1 + amp * math.sin(t * math.pi * 2 * hz) * 0.5 \
            + amp * math.sin(t * math.pi * 2 * hz * 2.7) * 0.5
        return ImageEnhance.Brightness(img).enhance(k)
    return f


def dust(count=48, speed=0.16, seed=4, size=(0.4, 1.0), alpha=0.22):
    """공기 중의 먼지가 아주 느리게 떠다닌다.

    처음엔 눈으로 만들었는데 시대·장소가 안 맞고 입자가 커서 눈에 띄었다.
    먼지는 **거의 안 보일 만큼 작고 느려야** 화면이 살아 있는 느낌만 남는다.
    """
    rnd = random.Random(seed)
    pts = [(rnd.random(), rnd.random(), rnd.uniform(*size),
            rnd.uniform(0.4, 1.4), rnd.uniform(0, 6.28)) for _ in range(count)]

    def f(img, t, fi):
        w, h = img.size
        layer = img.copy()
        d = ImageDraw.Draw(layer)
        for px, py, r, v, ph in pts:
            y = (py + t * speed * v) % 1.0
            x = (px + math.sin(t * 1.6 + ph) * 0.012) % 1.0
            cx, cy = x * w, y * h
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(206, 197, 178))
        return Image.blend(img, layer.filter(ImageFilter.GaussianBlur(0.7)), alpha)
    return f
