"""재생목록 커버 이미지 생성.

⚠️ 유튜브는 재생목록에 **이미지를 직접 올리는 칸이 없다.** 재생목록 썸네일은
그 안에 든 동영상 중 하나에서 고르게 되어 있다. 그래서 이 커버는 두 가지로 쓴다.

  1. **세로 1080x1920** — 재생목록 첫 편(또는 대표 편)의 맞춤 썸네일로 올린다.
     그 썸네일이 곧 재생목록 표지로 노출된다. 이게 실제 경로다.
  2. **가로 1280x720** — 커뮤니티 게시물·외부 공유·스튜디오가 가로 썸네일을
     요구하는 자리에 쓴다.

색·질감은 영상과 같은 세계를 써야 하므로 archive_layout / make_channel_banner를
그대로 재사용한다. 실존 인물 얼굴은 쓸 수 없으므로(PRD 5항) 여기서도 빈 명패가 배경이다.

**8장은 한 벌이다.** 제목 크기를 편마다 따로 맞추면 나란히 놓았을 때 글자 크기가
들쭉날쭉해 세트로 안 읽힌다. 가장 긴 제목이 들어가는 크기 하나를 구해 전부에 쓴다.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import archive_layout as A
import make_channel_banner as B

MARK = "이름을 부르다"

# (파일명, 재생목록 제목, 한 줄 설명)
# 제목의 줄바꿈은 의미 단위로 직접 넣는다. 자동 줄바꿈에 맡기면
# '나라가 무너질 / 때 / 총을 든 사람들'처럼 끊긴다.
PLAYLISTS = [
    ("00_all",      "전부 부른\n이름",                 "지금까지 부른 모든 이름"),
    ("01_uiyeol",   "폭탄을 든\n사람들",               "한 번의 기회에 모든 것을 걸었다"),
    ("02_women",    "그 여자의\n이름",                 "기록이 가장 적게 남은 자리"),
    ("03_foreign",  "조선을 도운\n이방인",             "조선 사람이 아니었던 사람들"),
    ("04_uibyeong", "나라가 무너질 때\n총을 든 사람들", "군인이 아니었던 이들이 먼저 싸웠다"),
    ("05_culture",  "붓과 노래로\n싸웠다",             "언론·교육·문화·종교로 싸운 사람들"),
    ("06_manju",    "만주와\n연해주에서",              "국경을 넘어 싸운 사람들"),
    ("07_group",    "함께 불러야 할\n이름들",          "한 편에 세 사람"),
]


def _ink(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1], box[0], box[1]


BLOCK_MAX = 0.72        # 글자 덩어리가 차지해도 되는 세로 비율. 나머지는 여백.


def _layout(draw, W, H, title, sub, size):
    """한 장의 글자 배치를 계산한다. 크기 결정과 그리기가 같은 식을 쓰게 한다.

    모든 치수를 제목 크기에 비례시킨다. 화면 높이에 매면 세로 1080x1920과
    가로 1280x720이 서로 다른 디자인처럼 보인다 — 같은 도안의 확대·축소여야 한다.
    """
    f_mark = A.load(A.NOTO_SERIF, int(size * 0.36), weight=400)
    f_title = A.load(A.NOTO_SERIF, size, weight=700)
    f_sub = A.load(A.NOTO_SERIF, int(size * 0.40), weight=400)

    lines = title.split("\n")
    sub_lines = A.wrap(draw, sub, f_sub, W * 0.84)

    g = dict(
        f_mark=f_mark, f_title=f_title, f_sub=f_sub,
        lines=lines, sub_lines=sub_lines,
        lh=int(size * 1.26), sub_lh=int(size * 0.57),
        gap_m=int(size * 0.48), rule_gap=int(size * 0.45),
        rule_h=max(3, int(size * 0.068)), gap_s=int(size * 0.45),
    )

    # 각 줄은 잉크 상단을 y + i*lh 에 맞춰 그린다. 따라서 블록의 실제 높이는
    # 마지막 줄의 잉크 높이까지이고, 줄간격 여백이 아래로 남지 않는다.
    g["mark_h"] = _ink(draw, MARK, f_mark)[1]
    g["title_h"] = g["lh"] * (len(lines) - 1) + _ink(draw, lines[-1], f_title)[1]
    g["sub_h"] = g["sub_lh"] * (len(sub_lines) - 1) + _ink(draw, sub_lines[-1], f_sub)[1]
    g["block"] = (g["mark_h"] + g["gap_m"] + g["title_h"] + g["rule_gap"]
                  + g["rule_h"] + g["gap_s"] + g["sub_h"])
    g["widest"] = max(_ink(draw, l, f_title)[0] for l in lines)
    return g


def shared_title_size(W, H, items):
    """8장 전부가 폭에도 높이에도 들어가는 가장 큰 크기 하나를 구한다.

    상한을 세로 기준(H)으로만 잡으면 가로 1280x720에서 폭이 남는데도 글자가
    안 자라고, 폭만 보면 이번엔 위아래가 꽉 차 여백이 사라진다. 둘 다 본다.
    """
    draw = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    max_w = W * 0.86
    size = int(H * 0.22)
    while size > int(H * 0.035):
        gs = [_layout(draw, W, H, t, s, size) for _, t, s in items]
        if (all(draw.textlength(l, font=g["f_title"]) <= max_w
                for g in gs for l in g["lines"])
                and max(g["block"] for g in gs) <= H * BLOCK_MAX):
            return size
        size -= 2
    return size


def _backdrop(W, H, seed):
    """명패 몇 장을 흩은 배경. 가운데는 글자가 앉을 자리라 비워 둔다."""
    canvas = A.make_paper(W, H, seed=seed)

    s = min(W, H)
    layout = [
        # 네 귀퉁이로 밀어 둔다 — 안쪽에 두면 제목과 겹쳐 지저분해진다
        (W * 0.09, H * 0.13, s * 0.30, s * 0.38, -5.0, 0.42),
        (W * 0.93, H * 0.19, s * 0.24, s * 0.30, 4.0, 0.30),
        (W * 0.91, H * 0.86, s * 0.30, s * 0.38, 5.5, 0.38),
        (W * 0.10, H * 0.89, s * 0.23, s * 0.29, -4.0, 0.26),
    ]
    for i, (cx, cy, pw, ph, rot, op) in enumerate(layout):
        card, mask = B._plate(int(pw), int(ph), seed + i * 7)
        card = card.rotate(rot, Image.BICUBIC, expand=True)
        mask = mask.rotate(rot, Image.BICUBIC, expand=True)
        mask = mask.point(lambda p, o=op: int(p * o)).filter(ImageFilter.GaussianBlur(1.2))
        canvas.paste(card, (int(cx - card.width / 2), int(cy - card.height / 2)), mask)

    # 가운데를 눌러 글자 대비를 만든다 (배너와 같은 방식)
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse(
        [W * 0.5 - W * 0.66, H * 0.5 - H * 0.30,
         W * 0.5 + W * 0.66, H * 0.5 + H * 0.30], fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(min(W, H) * 0.14))
    return Image.composite(ImageEnhance.Brightness(canvas).enhance(0.46), canvas, glow)


def cover(out_path, title, sub, W, H, size, seed=7):
    canvas = _backdrop(W, H, seed)
    draw = ImageDraw.Draw(canvas)
    cx = W / 2

    g = _layout(draw, W, H, title, sub, size)
    y = (H - g["block"]) / 2 - H * 0.012    # 시각 중심은 기하 중심보다 살짝 위

    B._tracked(draw, (0, y), MARK, g["f_mark"], B.GOLD,
               track=int(size * 0.14), anchor_center_x=cx)
    y += g["mark_h"] + g["gap_m"]

    for i, line in enumerate(g["lines"]):
        w, _, ox, oy = _ink(draw, line, g["f_title"])
        draw.text((cx - w / 2 - ox, y + i * g["lh"] - oy), line,
                  font=g["f_title"], fill=B.IVORY)
    y += g["title_h"] + g["rule_gap"]

    rule_w = int(g["widest"] * 1.04)
    draw.rectangle([cx - rule_w / 2, y, cx + rule_w / 2, y + g["rule_h"]], fill=B.GOLD)
    y += g["rule_h"] + g["gap_s"]

    for i, line in enumerate(g["sub_lines"]):
        B._tracked(draw, (0, y + i * g["sub_lh"]), line, g["f_sub"], B.DIM,
                   track=int(size * 0.03), anchor_center_x=cx)

    n = A._noise(W // 2, H // 2, 96, 160, seed + 5).resize((W, H), Image.BICUBIC)
    canvas = Image.blend(canvas, Image.merge("RGB", (n,) * 3), 0.055)

    canvas.save(out_path)
    return out_path


def contact_sheet(paths, out_path, cols=4, cell_w=270):
    """8장을 한 판에 늘어놓아 한 벌로 읽히는지 본다."""
    imgs = [Image.open(p).convert("RGB") for p in paths]
    ch = int(cell_w * imgs[0].height / imgs[0].width)
    rows = (len(imgs) + cols - 1) // cols
    pad = 16

    sheet = Image.new("RGB",
                      (cols * cell_w + pad * (cols + 1), rows * ch + pad * (rows + 1)),
                      (18, 17, 16))
    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        sheet.paste(im.resize((cell_w, ch), Image.LANCZOS),
                    (pad + c * (cell_w + pad), pad + r * (ch + pad)))
    sheet.save(out_path)
    return out_path


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    outdir = os.path.join(base, "assets", "playlists")
    os.makedirs(outdir, exist_ok=True)

    sizes = {(1080, 1920): shared_title_size(1080, 1920, PLAYLISTS),
             (1280, 720): shared_title_size(1280, 720, PLAYLISTS)}
    print("공통 제목 크기:", {f"{w}x{h}": s for (w, h), s in sizes.items()})

    made = {"v": [], "h": []}
    for i, (slug, title, sub) in enumerate(PLAYLISTS):
        seed = 7 + i * 13               # 편마다 종이 얼룩·명패 결을 다르게
        made["v"].append(cover(os.path.join(outdir, f"{slug}_1080x1920.png"),
                               title, sub, 1080, 1920, sizes[(1080, 1920)], seed))
        made["h"].append(cover(os.path.join(outdir, f"{slug}_1280x720.png"),
                               title, sub, 1280, 720, sizes[(1280, 720)], seed))
        print("saved:", slug)

    prev = os.path.join(base, "output")
    print("preview:", contact_sheet(made["v"], os.path.join(prev, "playlist_covers_preview.png")))
    print("preview:", contact_sheet(made["h"], os.path.join(prev, "playlist_covers_h_preview.png"),
                                    cols=2, cell_w=560))
