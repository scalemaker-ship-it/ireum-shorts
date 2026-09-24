"""모션 후보 데모 — 세 가지를 얹어보고 비교한다.

지금은 켄번스 줌 6%가 전부라 모든 컷이 같은 방식으로 커지기만 한다.
정지 사진이 계속 나오는 형식이라 움직임이 단조로우면 금방 지루해진다.
"""
import os, subprocess, sys, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageChops
import archive_layout as A
from archive_layout import (build_card, paste_card, make_paper, draw_title, draw_year,
                            draw_caption, caption_pages, card_pos, _noise)
from render_archive_video import kenburns, kb_pos

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FPS = 30


def grain_tiles(n=10, seed=99):
    """움직이는 필름 그레인. 정지 사진에 얹으면 '영사되는 필름'처럼 보인다.

    매 프레임 새로 만들면 너무 느려서 몇 장을 미리 만들어 돌려 쓴다.
    """
    return [_noise(A.W // 3, A.H // 3, 96, 160, seed + i)
            .resize((A.W, A.H), Image.BILINEAR) for i in range(n)]


def apply_grain(frame, tile, amount=0.055):
    return Image.blend(frame, Image.merge("RGB", (tile,) * 3), amount)


def kb(card, mask, t, zoom, out=False, drift=(0, 0)):
    """줌 방향과 미세한 표류를 더한 켄번스."""
    tt = (1 - t) if out else t
    c, m = kenburns(card, mask, tt, zoom)
    x, y = kb_pos(card, c)
    return c, m, (x + int(drift[0] * t), y + int(drift[1] * t))


def main():
    d = json.load(open(os.path.join(BASE, "drafts/script_dok_01_kang.json"), encoding="utf-8"))
    title = d["display_title"]
    segs = [s for s in d["segments"] if s["id"] in ("03_setup", "04_hint1", "05_hint2")]
    paper = make_paper(A.W, A.H)
    tiles = grain_tiles()

    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    frames = os.path.join(BASE, "output/video/_demo")
    os.makedirs(frames, exist_ok=True)
    for f in os.listdir(frames):
        os.remove(os.path.join(frames, f))

    idx = 0
    for si, seg in enumerate(segs):
        card, mask, graded = build_card(os.path.join(BASE, seg["image"]),
                                        seed=abs(hash(seg["id"])) % 997)
        pages, counts, font, top = caption_pages(seg["text"], 46, 400)
        n = int(4.6 * FPS)
        rnd = random.Random(si)
        zoom_out = (si % 2 == 1)                       # 컷마다 줌 방향을 바꾼다
        drift = (rnd.choice([-14, 14]), rnd.choice([-10, 10]))   # 아주 느린 표류
        for i in range(n):
            t = i / max(1, n - 1)
            if mode in ("zoom", "all"):
                c, m, pos = kb(card, mask, t, 0.06, out=zoom_out, drift=drift)
            else:
                c, m = kenburns(card, mask, t, 0.06); pos = kb_pos(card, c)
            fr = paste_card(paper.copy(), c, m, graded, pos=pos)
            draw_title(fr, title); draw_year(fr, seg["year"])
            reveal = int(sum(counts) * min(1.0, i / (n * 0.88)))
            from archive_layout import page_at
            pi, r = page_at(counts, reveal)
            draw_caption(fr, pages[pi], font, 46, reveal=r,
                         cursor=reveal < sum(counts), top=top)
            if mode in ("grain", "all"):
                fr = apply_grain(fr, tiles[idx % len(tiles)])
            fr.save(os.path.join(frames, f"{idx:05d}.png"))
            idx += 1

    out = os.path.join(BASE, f"output/preview/motion_{mode}.mp4")
    subprocess.run(["ffmpeg", "-y", "-framerate", str(FPS),
                    "-i", os.path.join(frames, "%05d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", out],
                   check=True, capture_output=True)
    for f in os.listdir(frames):
        os.remove(os.path.join(frames, f))
    print(f"{idx} 프레임 → {out}")


if __name__ == "__main__":
    main()
