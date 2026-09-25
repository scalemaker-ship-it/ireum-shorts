"""v3 모션 효과 — 이미지 나열이 아니라 영상처럼 보이게 (2026-09-25 사용자 요청).

전부 프레임 단위로 계산하는 값싼 합성이다. 외부 영상·AI 동영상 생성 없이 사진 한 장을 '찍고 있는 화면'처럼 만든다.

- handheld(fi)          손에 든 카메라처럼 미세하게 떠다니는 흔들림 (px)
- Particles             먼지 / 불씨 / 비 / 눈 — 사진 밴드 위에 얹는다
- light_leak()          필름에 빛이 새는 따뜻한 번짐이 천천히 화면을 가로지른다
- push_transition()     줌 푸시 전환 — 앞 그림이 밀려 들어가며 번쩍, 새 그림이 당겨져 나온다
- pop()                 자막 한 줄이 아래에서 튀어 오른다
- shake(t)              폭발·총성 순간의 화면 흔들림 (감쇠)
"""
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


def ease(k):
    k = max(0.0, min(1.0, k))
    return k * k * (3 - 2 * k)


def ease_out(k, p=3):
    k = max(0.0, min(1.0, k))
    return 1 - (1 - k) ** p


# ───────── 카메라 ─────────

def handheld(fi, amp=5.0, seed=0):
    """서로 다른 주기의 사인 셋을 겹친 저주파 흔들림. 규칙적으로 보이지 않게 비율을 무리수로 둔다."""
    t = fi / 30.0 + seed * 7.3
    dx = amp * (0.55 * math.sin(t * 0.83) + 0.30 * math.sin(t * 1.97 + 1.1) + 0.15 * math.sin(t * 3.71 + 2.3))
    dy = amp * (0.55 * math.sin(t * 0.67 + 0.4) + 0.30 * math.sin(t * 2.29 + 0.7) + 0.15 * math.sin(t * 4.13 + 1.9))
    return dx, dy


def shake(t, amp=22, decay=7.0, hz=19):
    """t초 전에 충격이 있었을 때의 흔들림. 0.6초 안에 가라앉는다."""
    if t < 0 or t > 0.7:
        return 0, 0
    a = amp * math.exp(-decay * t)
    return int(a * math.sin(t * hz * 6.28)), int(a * 0.7 * math.cos(t * hz * 5.1))


# ───────── 입자 ─────────

class Particles:
    """kind: dust(떠다니는 먼지) / embers(위로 솟는 불씨) / rain(비) / snow(눈) / smoke(연기 결)."""

    def __init__(self, kind, size, seed=1, n=None):
        self.kind, self.size = kind, size
        w, h = size
        rnd = random.Random(seed)
        n = n or {"dust": 70, "embers": 55, "rain": 160, "snow": 90, "smoke": 0}.get(kind, 60)
        self.p = [(rnd.random() * w, rnd.random() * h, rnd.uniform(0.5, 1.5), rnd.uniform(0, 6.28))
                  for _ in range(n)]
        self.smoke = None
        if kind == "smoke":
            noise = np.random.default_rng(seed).integers(0, 255, (h // 16, w // 16)).astype(np.uint8)
            m = Image.fromarray(noise).resize((w * 2, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(18))
            arr = np.asarray(m).astype(np.float32)
            arr = np.clip((arr - 118) * 2.2, 0, 255)
            self.smoke = Image.fromarray(arr.astype(np.uint8))

    def apply(self, img, fi):
        w, h = self.size
        t = fi / 30.0
        if self.kind == "smoke":
            ox = int((t * 38) % w)
            band = self.smoke.crop((ox, 0, ox + w, h)).point(lambda v: int(v * 0.28))
            img = img.copy()
            img.paste(Image.new("RGB", (w, h), (205, 198, 186)), (0, 0), band)
            return img
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for x0, y0, s, ph in self.p:
            if self.kind == "dust":
                x = (x0 + math.sin(t * 0.7 + ph) * 18 + t * 6 * s) % w
                y = (y0 + t * 9 * s) % h
                r = 1.0 + s
                d.ellipse([x - r, y - r, x + r, y + r], fill=(235, 228, 210, int(70 + 50 * s)))
            elif self.kind == "embers":
                x = (x0 + math.sin(t * 1.6 + ph) * 22) % w
                y = (y0 - t * 70 * s) % h
                r = 1.2 + s * 1.3
                flick = 0.6 + 0.4 * math.sin(t * 9 + ph * 3)
                d.ellipse([x - r * 2.2, y - r * 2.2, x + r * 2.2, y + r * 2.2], fill=(255, 120, 30, int(40 * flick)))
                d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 200, 90, int(210 * flick)))
            elif self.kind == "rain":
                x = (x0 + t * 60) % w
                y = (y0 + t * 900 * s) % h
                d.line([(x, y), (x - 6, y + 28 * s)], fill=(210, 215, 225, 90), width=2)
            elif self.kind == "snow":
                x = (x0 + math.sin(t * 0.9 + ph) * 25) % w
                y = (y0 + t * 45 * s) % h
                r = 1.5 + s * 1.8
                d.ellipse([x - r, y - r, x + r, y + r], fill=(245, 245, 250, 200))
        if self.kind in ("embers", "dust"):
            layer = layer.filter(ImageFilter.GaussianBlur(0.8))
        out = img.convert("RGBA")
        out.alpha_composite(layer)
        return out.convert("RGB")


# ───────── 빛번짐 ─────────

_LEAK = {}


def light_leak(img, fi, seed=0, strength=0.22, period=6.0):
    """따뜻한 빛 덩어리가 period초에 한 번 화면을 가로지른다. 흑백 모드에서도 미세하게 따뜻해진다."""
    w, h = img.size
    key = (w, h)
    if key not in _LEAK:
        g = Image.new("L", (w, h), 0)
        ImageDraw.Draw(g).ellipse([-w * 0.25, -h * 0.35, w * 0.45, h * 1.1], fill=255)
        _LEAK[key] = g.filter(ImageFilter.GaussianBlur(w * 0.18))
    t = (fi / 30.0 + seed * 2.1) % period / period          # 0→1
    a = math.sin(math.pi * t) ** 2 * strength
    if a < 0.01:
        return img
    dx = int((t * 1.4 - 0.4) * w)
    mask = Image.new("L", (w, h), 0)
    mask.paste(_LEAK[key], (dx, 0))
    mask = mask.point(lambda v: int(v * a))
    warm = Image.new("RGB", (w, h), (255, 176, 96))
    return Image.composite(Image.blend(img, warm, 0.55), img, mask)


# ───────── 전환 ─────────

def _zoom(img, s):
    w, h = img.size
    if abs(s - 1) < 1e-3:
        return img
    nw, nh = int(w * s), int(h * s)
    z = img.resize((nw, nh), Image.BILINEAR)
    x0, y0 = (nw - w) // 2, (nh - h) // 2
    return z.crop((x0, y0, x0 + w, y0 + h))


def push_transition(prev, cur, k):
    """k: 0→1. 앞 그림은 1.0→1.22로 밀려 들어가며 흐려지고, 새 그림은 1.16→1.0으로 당겨져 나온다.
    가운데에서 한 번 번쩍인다. 줌 블러는 배율이 조금 다른 두 장을 겹쳐 흉내 낸다."""
    e = ease(k)
    a = _zoom(prev, 1 + 0.22 * e)
    a = Image.blend(a, _zoom(prev, 1 + 0.30 * e), 0.5 * e)
    b = _zoom(cur, 1.16 - 0.16 * e)
    b = Image.blend(b, _zoom(cur, 1.24 - 0.24 * e), 0.5 * (1 - e))
    out = Image.blend(a, b, e)
    flash = math.sin(math.pi * k) ** 2
    return ImageEnhance.Brightness(out).enhance(1 + 0.45 * flash)


# ───────── 자막 ─────────

def pop(layer, k):
    """자막 레이어(RGBA)를 튀어 오르게: 배율 0.82→1.06→1.0, 아래 24px에서 올라오며 불투명해진다."""
    if k >= 1:
        return layer, 0
    e = ease_out(k)
    s = 0.82 + 0.24 * e - 0.06 * max(0.0, (k - 0.6) / 0.4)
    w, h = layer.size
    nw, nh = max(1, int(w * s)), max(1, int(h * s))
    z = layer.resize((nw, nh), Image.BILINEAR)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(z, ((w - nw) // 2, (h - nh) // 2))
    alpha = out.getchannel("A").point(lambda v: int(v * min(1.0, k * 2.5)))
    out.putalpha(alpha)
    return out, int(24 * (1 - e))


# ───────── 모션그래픽 (2026-09-26 사용자 — "모션그래픽처럼") ─────────
# 전부 전체 프레임(1080×1920) 위에 얹는다. band = 사진 밴드 (x0, y0, x1, y1).

def _rgba_text(text, font, fill, pad=0):
    d = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    l, t, r, b = d.textbbox((0, 0), text, font=font)
    im = Image.new("RGBA", (r - l + pad * 2, b - t + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((pad - l, pad - t), text, font=font, fill=fill)
    return im


def tag(fr, text, since, band, font, ivory=(237, 230, 214), red=(196, 42, 42)):
    """장소 태그 — 사진 왼쪽 아래로 미끄러져 들어와 머문다."""
    if since < 0:
        return fr
    k = ease_out(since / 0.35)
    txt = _rgba_text(text, font, ivory)
    pw, ph = txt.width + 44, txt.height + 26
    box = Image.new("RGBA", (pw, ph), (10, 9, 8, 190))
    ImageDraw.Draw(box).rectangle([0, 0, 7, ph], fill=red + (255,))
    box.alpha_composite(txt, (26, 13))
    x = int(60 - (pw + 60) * (1 - k))
    y = band[3] - ph - 150
    out = fr.convert("RGBA")
    box.putalpha(box.getchannel("A").point(lambda v: int(v * min(1.0, k * 1.5))))
    out.alpha_composite(box, (max(-pw, x), y))
    return out.convert("RGB")


def callout(fr, text, since, dur, band, font, ivory=(237, 230, 214), red=(196, 42, 42)):
    """키워드 콜아웃 — 크게 떴다가(1.25→1.0) 빨간 밑줄이 그어지고, dur 끝에서 사라진다."""
    if since < 0 or since > dur:
        return fr
    k_in = ease_out(since / 0.28)
    k_out = 1 - ease(max(0.0, (since - (dur - 0.3)) / 0.3))
    a = k_in * k_out
    txt = _rgba_text(text, font, ivory, pad=10)
    s = 1.25 - 0.25 * k_in
    txt = txt.resize((max(1, int(txt.width * s)), max(1, int(txt.height * s))), Image.BILINEAR)
    cx, cy = (band[0] + band[2]) // 2, (band[1] + band[3]) // 2
    # 뒤에 어두운 띠를 깔아 사진 위에서도 읽히게
    plate = Image.new("RGBA", (fr.width, txt.height + 70), (8, 7, 6, int(150 * a)))
    out = fr.convert("RGBA")
    out.alpha_composite(plate, (0, cy - plate.height // 2))
    txt.putalpha(txt.getchannel("A").point(lambda v: int(v * a)))
    out.alpha_composite(txt, (cx - txt.width // 2, cy - txt.height // 2 - 8))
    k_line = ease(max(0.0, (since - 0.2) / 0.35))
    if k_line > 0:
        lw = int(txt.width * 0.9 * k_line)
        ly = cy + txt.height // 2 + 4
        ImageDraw.Draw(out).rectangle([cx - int(txt.width * 0.45), ly, cx - int(txt.width * 0.45) + lw, ly + 8],
                                      fill=red + (int(255 * a),))
    return out.convert("RGB")


def stamp(fr, text, since, band, font, red=(196, 42, 42)):
    """도장 — 크게(2.0) 기울어진 채 내려와 쾅 찍히고 그대로 남는다. 찍히는 순간 살짝 흔들린다."""
    if since < 0:
        return fr, (0, 0)
    k = ease_out(min(1.0, since / 0.16), p=2)
    txt = _rgba_text(text, font, red + (255,), pad=18)
    w, h = txt.width + 20, txt.height + 20
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([4, 4, w - 5, h - 5], radius=14, outline=red + (255,), width=8)
    im.alpha_composite(txt, (10, 10))
    # 도장 잉크 결 — 군데군데 빠진 느낌
    grain = Image.effect_noise((w, h), 40).point(lambda v: 255 if v > 55 else 170)   # 잉크가 조금만 빠지게
    im.putalpha(Image.composite(im.getchannel("A"), Image.new("L", (w, h), 0), grain))
    s = 2.0 - 1.0 * k
    im = im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.BILINEAR).rotate(-9, expand=True, resample=Image.BICUBIC)
    im.putalpha(im.getchannel("A").point(lambda v: int(v * min(1.0, k * 1.4))))
    x = (band[0] + band[2]) // 2 - im.width // 2 + 120       # 가운데보다 살짝 오른쪽
    y = (band[1] + band[3]) // 2 - im.height // 2 - 40
    out = fr.convert("RGBA")
    out.alpha_composite(im, (x, y))
    jolt = shake(since - 0.16, amp=10, decay=12) if since > 0.16 else (0, 0)
    return out.convert("RGB"), jolt
