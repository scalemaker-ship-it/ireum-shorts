"""회차별 대본과 검증 기록을 모바일에서 읽는 HTML 한 장으로 굽는다.

이 채널은 실존 인물을 다루므로 '무엇을 어느 사료로 확인했는가'와
'무엇을 창작으로 판정해 지웠는가'가 대본만큼 중요하다. 그래서 잡학쿠키
대본집과 달리 검증 기록을 한 화면에 같이 싣는다.

    python3 scripts/build_archive_page.py
    -> output/자료집/index.html

새 회차를 만들 때마다 이걸 다시 돌리고 같은 Artifact URL로 재배포한다.
"""

import glob
import html
import json
import os
import re
import sys
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_info import build as build_upload   # noqa: E402

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DRAFTS = os.path.join(BASE, "drafts")
FINALS = os.path.join(BASE, "output", "최종본")
OUT = os.path.join(BASE, "output", "자료집", "index.html")

# 검증 필드 중 '지운 것'을 담는 키. 값이 리스트다.
CUT_KEYS = ("삭제된_창작", "삭제된_해석", "쓰지_않은_것")


def e(s):
    return html.escape(str(s), quote=True)


def duration(path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, check=True).stdout.strip()
        return float(out)
    except Exception:
        return None


def split_source(text):
    """검증 값 뒤에 붙은 출처를 떼어낸다. '내용 — 출처' 형태로 써 왔다."""
    for sep in (" — ", " - "):
        if sep in text:
            body, src = text.rsplit(sep, 1)
            if len(src) < 60:
                return body, src
    return text, ""


def linkify(src):
    """'이름 https://...' 형태의 출처 문자열을 링크로 만든다."""
    m = re.search(r"(https?://\S+)", src)
    if not m:
        return e(src), ""
    return e(src[:m.start()].strip()), m.group(1)


def load():
    made = {os.path.basename(p)[:-4]: p for p in glob.glob(os.path.join(FINALS, "*.mp4"))}
    rows = []
    for path in sorted(glob.glob(os.path.join(DRAFTS, "script_dok_*.json"))):
        d = json.load(open(path, encoding="utf-8"))
        segs = d.get("segments", [])
        out_rel = d.get("output", "")
        slug = os.path.basename(out_rel)[:-4] if out_rel else ""
        mp4 = made.get(slug)
        subject = d.get("subject", "")
        rows.append({
            "num": d.get("episode", 0),
            "title": d.get("display_title") or d.get("title", ""),
            "name": subject.split(" (")[0],
            "detail": subject[len(subject.split(" (")[0]):].strip(" ()"),
            "award": d.get("award", ""),
            "segments": segs,
            "chars": sum(len(s.get("text", "")) for s in segs),
            "sources": d.get("sources", []),
            "verified": d.get("verified", {}),
            "secs": duration(mp4) if mp4 else None,
            "has_video": mp4 is not None,
            "checked": d.get("verified", {}).get("_검증일", ""),
            "upload": build_upload(d),
        })
    rows.sort(key=lambda r: r["num"], reverse=True)
    return rows


def render_script(segs):
    out = []
    for i, s in enumerate(segs):
        cls = "cut is-reveal" if "reveal" in s.get("id", "") else "cut"
        out.append(
            f'<div class="{cls}">'
            f'<div class="stamp"><span class="n">{i + 1:02d}</span>'
            f'<span class="yr">{e(s.get("year", ""))}</span></div>'
            f'<p>{e(s.get("text", ""))}</p>'
            f"</div>")
    return "".join(out)


def render_verified(v):
    facts, cuts = [], []
    for k, val in v.items():
        if k.startswith("_"):
            continue
        if k in CUT_KEYS:
            cuts += list(val) if isinstance(val, list) else [val]
            continue
        for item in (val if isinstance(val, list) else [val]):
            body, src = split_source(str(item))
            src_html = f'<span class="src">{e(src)}</span>' if src else ""
            facts.append(f'<div class="fact"><dt>{e(k)}</dt>'
                         f"<dd>{e(body)}{src_html}</dd></div>")
    blocks = ""
    if facts:
        blocks += f'<dl class="facts">{"".join(facts)}</dl>'
    if cuts:
        items = "".join(f"<li>{e(c)}</li>" for c in cuts)
        blocks += (f'<div class="cuts"><h4>쓰지 않은 것</h4>'
                   f"<ul>{items}</ul></div>")
    return blocks


def render_sources(srcs):
    out = []
    for s in srcs:
        label, url = linkify(s)
        out.append(f'<li><a href="{e(url)}" target="_blank" rel="noopener">{label}</a></li>'
                   if url else f"<li>{label}</li>")
    return "".join(out)


def render_upload(u):
    """업로드할 때 그대로 복사해 쓰는 값들. **설명란에 URL은 넣지 않는다**(upload_info 참고)."""
    def block(label, text):
        return f'<div class="ub"><h4>{label}</h4><pre>{e(text)}</pre></div>'
    parts = [block("제목", u["title"]), block("설명란", u["description"])]
    if u["tags"]:
        parts.append(block("태그", ", ".join(u["tags"])))
    parts.append(block("고정 댓글", u["pinned"]))
    if u["playlists"]:
        parts.append('<div class="ub"><h4>재생목록</h4><ul>'
                     + "".join(f"<li>{e(p)}</li>" for p in u["playlists"]) + "</ul></div>")
    parts.append('<div class="ub"><h4>업로드 설정</h4><ul>'
                 + "".join(f"<li>{e(x)}</li>" for x in u["settings"]) + "</ul></div>")
    return "".join(parts)


def render(r):
    dur = f"{r['secs']:.0f}초" if r["secs"] else "미제작"
    badge = ('<span class="badge badge--done">영상 완성</span>' if r["has_video"]
             else '<span class="badge">대본만</span>')
    ver = render_verified(r["verified"])
    return f"""<article class="ep" data-video="{'y' if r['has_video'] else 'n'}">
<header class="ep-head">
  <div class="ep-top"><span class="epno">{r['num']:02d}화</span>{badge}</div>
  <h2>{e(r['title'])}</h2>
  <p class="who"><b>{e(r['name'])}</b><span>{e(r['detail'])}</span></p>
  <div class="facts-bar">
    <span>{len(r['segments'])}컷</span><span>{r['chars']}자</span><span>{dur}</span>
    {f"<span>{e(r['award'])}</span>" if r['award'] else ""}
  </div>
</header>

<div class="script">{render_script(r['segments'])}</div>

<details class="rec">
  <summary><span>검증 기록</span>{f'<em>{e(r["checked"])}</em>' if r["checked"] else ""}</summary>
  <div class="rec-body">
    {ver}
    <div class="srcs"><h4>출처</h4><ul>{render_sources(r['sources'])}</ul></div>
  </div>
</details>

<details class="rec rec--up">
  <summary><span>업로드 정보</span><em>복사해서 쓰는 값</em></summary>
  <div class="rec-body">{render_upload(r['upload'])}</div>
</details>
</article>"""


def build():
    rows = load()
    done = sum(1 for r in rows if r["has_video"])
    stamp = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")

    doc = f"""<title>이름을 부르다 기록집</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&family=Noto+Sans+KR:wght@300;400;500&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
/* 어두운 기록 사진 쪽이 이 시리즈의 기본 얼굴이라 :root를 어둡게 두고,
   밝은 테마는 '오래된 종이' 쪽으로 뒤집는다. */
:root {{
  --ground:#0A0908; --surface:#141210; --raise:#1C1916;
  --rule:#2B2620; --rule-soft:#1E1B16;
  --ink:#B2A999; --ink-strong:#DCD4C4; --muted:#6F675B;
  --accent:#A8843C; --accent-dim:#6B5426; --accent-wash:#1E1809;
  --strike:#8A5147;
  --serif:"Nanum Myeongjo",'Apple SD Gothic Neo',serif;
  --sans:"Noto Sans KR",'Apple SD Gothic Neo',system-ui,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,monospace;
}}
@media (prefers-color-scheme:light) {{
  :root:not([data-theme="dark"]) {{
    --ground:#E7E1D3; --surface:#F1ECE0; --raise:#E2DACA;
    --rule:#CEC5AF; --rule-soft:#DED6C4;
    --ink:#2C271E; --ink-strong:#14110C; --muted:#6A6152;
    --accent:#7C5A1C; --accent-dim:#A08B5E; --accent-wash:#EFE6CE;
    --strike:#8A3F32;
  }}
}}
:root[data-theme="light"] {{
  --ground:#E7E1D3; --surface:#F1ECE0; --raise:#E2DACA;
  --rule:#CEC5AF; --rule-soft:#DED6C4;
  --ink:#2C271E; --ink-strong:#14110C; --muted:#6A6152;
  --accent:#7C5A1C; --accent-dim:#A08B5E; --accent-wash:#EFE6CE;
  --strike:#8A3F32;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--sans); font-weight:300; font-size:16px; line-height:1.72;
  -webkit-text-size-adjust:100%;
}}
.wrap {{ max-width:40rem; margin:0 auto; padding:2.5rem 1.15rem 4.5rem; }}

/* --- 머리 --- */
.masthead {{ margin-bottom:2.25rem; }}
.rule-title {{ display:flex; align-items:center; gap:.9rem; }}
.rule-title::before, .rule-title::after {{
  content:""; height:1px; flex:1; background:var(--rule); min-width:1.5rem;
}}
h1 {{
  font-family:var(--serif); font-weight:700; font-size:1.5rem;
  letter-spacing:.14em; margin:0; white-space:nowrap; color:var(--ink-strong);
}}
.sub {{
  margin:.9rem 0 0; text-align:center; font-size:.82rem; color:var(--muted);
  line-height:1.65;
}}
.stampline {{
  display:block; font-family:var(--mono); font-size:.7rem;
  letter-spacing:.06em; margin-top:.35rem;
}}
.tally {{
  display:flex; justify-content:center; gap:2.25rem;
  margin-top:1.6rem; padding:1rem 0; border-block:1px solid var(--rule);
}}
.tally div {{ display:flex; flex-direction:column; align-items:center; gap:.2rem; }}
.tally b {{
  font-family:var(--mono); font-weight:500; font-size:1.35rem; line-height:1;
  color:var(--ink-strong); font-variant-numeric:tabular-nums;
}}
.tally span {{ font-size:.7rem; letter-spacing:.08em; color:var(--muted); }}

.filters {{ display:flex; justify-content:center; gap:.4rem; margin-top:1.4rem; }}
.filters button {{
  font:inherit; font-size:.78rem; letter-spacing:.03em; padding:.4rem .95rem;
  cursor:pointer; background:transparent; color:var(--muted);
  border:1px solid var(--rule); border-radius:1px;
}}
.filters button[aria-pressed="true"] {{
  color:var(--accent); border-color:var(--accent-dim); background:var(--accent-wash);
}}
.filters button:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}

/* --- 회차 --- */
.list {{ display:flex; flex-direction:column; gap:2.75rem; margin-top:2.25rem; }}
.ep[hidden] {{ display:none; }}
.ep-head {{ display:flex; flex-direction:column; gap:.5rem; }}
.ep-top {{ display:flex; align-items:center; gap:.7rem; }}
.epno {{
  font-family:var(--mono); font-size:.75rem; font-weight:500;
  letter-spacing:.1em; color:var(--accent);
}}
.badge {{
  font-size:.65rem; letter-spacing:.1em; padding:.15rem .5rem;
  border:1px solid var(--rule); color:var(--muted);
}}
.badge--done {{ border-color:var(--accent-dim); color:var(--accent); }}
.ep-head h2 {{
  font-family:var(--serif); font-weight:800; font-size:1.32rem; line-height:1.45;
  margin:0; color:var(--ink-strong); text-wrap:balance;
}}
.who {{ margin:0; display:flex; align-items:baseline; gap:.55rem; flex-wrap:wrap; }}
.who b {{ font-family:var(--serif); font-weight:700; font-size:1rem; color:var(--ink); }}
.who span {{ font-size:.76rem; color:var(--muted); font-variant-numeric:tabular-nums; }}
.facts-bar {{
  display:flex; flex-wrap:wrap; gap:.5rem 1.1rem; padding-top:.35rem;
  font-size:.73rem; color:var(--muted); font-variant-numeric:tabular-nums;
}}

/* --- 대본: 왼쪽 여백에 컷 번호와 연도 스탬프. 영상의 연도 표기를 그대로 옮겼다 --- */
.script {{
  display:flex; flex-direction:column; gap:1.15rem;
  margin-top:1.5rem; padding:1.5rem 1.25rem;
  background:var(--surface); border:1px solid var(--rule-soft);
}}
.cut {{ display:grid; grid-template-columns:3.1rem 1fr; gap:1rem; align-items:start; }}
.stamp {{ display:flex; flex-direction:column; gap:.15rem; padding-top:.3rem; }}
.n {{
  font-family:var(--mono); font-size:.68rem; color:var(--muted);
  font-variant-numeric:tabular-nums;
}}
.yr {{
  font-family:var(--serif); font-size:.78rem; color:var(--accent);
  border-bottom:1px solid var(--accent-dim); padding-bottom:.1rem;
  font-variant-numeric:tabular-nums; width:max-content;
}}
.cut p {{ margin:0; font-size:.98rem; }}
.cut.is-reveal p {{ color:var(--ink-strong); font-weight:400; }}
.cut.is-reveal {{
  border-left:2px solid var(--accent); margin-left:-1.25rem; padding-left:1.15rem;
}}

/* --- 검증 기록 --- */
.rec {{ margin-top:.85rem; border-top:1px solid var(--rule); }}
.rec summary {{
  display:flex; align-items:baseline; gap:.6rem; padding:.75rem 0;
  cursor:pointer; list-style:none; font-size:.8rem; letter-spacing:.06em;
  color:var(--accent);
}}
.rec summary::-webkit-details-marker {{ display:none; }}
.rec summary::after {{ content:"펼치기"; margin-left:auto; color:var(--muted); font-size:.72rem; }}
.rec[open] summary::after {{ content:"접기"; }}
.rec summary em {{ font-style:normal; font-family:var(--mono); font-size:.68rem; color:var(--muted); }}
.rec summary:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}
.rec-body {{ padding:.25rem 0 1.1rem; display:flex; flex-direction:column; gap:1.4rem; }}

.facts {{ margin:0; display:flex; flex-direction:column; gap:.85rem; }}
.fact {{ display:grid; grid-template-columns:5.2rem 1fr; gap:.9rem; align-items:start; }}
.fact dt {{
  font-size:.75rem; letter-spacing:.03em; color:var(--muted);
  padding-top:.15rem; overflow-wrap:anywhere;
}}
.fact dd {{ margin:0; font-size:.85rem; line-height:1.62; }}
.src {{ display:block; margin-top:.15rem; font-size:.72rem; color:var(--accent-dim); }}

.cuts h4, .srcs h4 {{
  margin:0 0 .6rem; font-size:.72rem; font-weight:500; letter-spacing:.1em;
  color:var(--muted);
}}
.cuts ul {{ margin:0; padding:0; list-style:none; display:flex; flex-direction:column; gap:.55rem; }}
.cuts li {{
  font-size:.83rem; line-height:1.6; padding-left:.9rem; position:relative;
  color:var(--muted); text-decoration:line-through;
  text-decoration-color:var(--strike); text-decoration-thickness:1px;
}}
.cuts li::before {{
  content:"×"; position:absolute; left:0; color:var(--strike);
  text-decoration:none; display:inline-block;
}}
.srcs ul {{ margin:0; padding:0; list-style:none; display:flex; flex-direction:column; gap:.4rem; }}
.srcs li {{ font-size:.8rem; line-height:1.55; }}
.srcs a {{ color:var(--ink); text-decoration:underline; text-decoration-color:var(--accent-dim); text-underline-offset:3px; }}
.srcs a:hover {{ color:var(--accent); }}
.srcs a:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}

/* --- 업로드 정보: 폰에서 길게 눌러 복사하는 블록이라 선택이 쉬워야 한다 --- */
.rec--up summary {{ color:var(--ink); }}
.ub {{ margin-bottom:1.1rem; }}
.ub h4 {{
  margin:0 0 .45rem; font-size:.72rem; font-weight:500; letter-spacing:.1em; color:var(--muted);
}}
.ub pre {{
  margin:0; padding:.85rem .9rem; background:var(--raise); border:1px solid var(--rule-soft);
  font-family:var(--mono); font-size:.76rem; line-height:1.62; color:var(--ink);
  white-space:pre-wrap; overflow-wrap:anywhere; user-select:all; -webkit-user-select:all;
}}
.ub ul {{ margin:0; padding-left:1.1rem; font-size:.83rem; }}
.ub li {{ margin-bottom:.25rem; }}

footer {{
  margin-top:3.5rem; padding-top:1.25rem; border-top:1px solid var(--rule);
  font-size:.73rem; line-height:1.75; color:var(--muted);
}}
@media (prefers-reduced-motion:reduce) {{ * {{ animation:none!important; transition:none!important; }} }}
</style>

<div class="wrap">
<header class="masthead">
  <div class="rule-title"><h1>이름을 부르다</h1></div>
  <p class="sub">독립운동가 한 사람을 1분 안에 부르는 기록.
    문장마다 사료를 대조하고, 근거를 못 대는 문장은 지운다.
    <span class="stampline">{stamp} 기준</span></p>
  <div class="tally">
    <div><b>{len(rows)}</b><span>회차</span></div>
    <div><b>{done}</b><span>영상 완성</span></div>
    <div><b>{len(rows) - done}</b><span>대본만</span></div>
  </div>
  <div class="filters">
    <button aria-pressed="true" data-f="all">전체</button>
    <button aria-pressed="false" data-f="y">영상 완성</button>
    <button aria-pressed="false" data-f="n">대본만</button>
  </div>
</header>

<div class="list" id="list">
{chr(10).join(render(r) for r in rows)}
</div>

<footer>
  나레이션 — 필재 · Typecast ssfm-v30 · 1~10화 1.15배속, 11화부터 1.25배속.
  왼쪽 세로선이 그어진 컷에서 이름을 처음 부른다.
  나무위키는 쓰지 않는다. 인물 초상은 퍼블릭 도메인·CC BY만 쓰고, 실존 인물의 얼굴은 AI로 만들지 않는다.
</footer>
</div>

<script>
const list = document.getElementById('list');
document.querySelectorAll('.filters button').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.filters button')
      .forEach(b => b.setAttribute('aria-pressed', String(b === btn)));
    const f = btn.dataset.f;
    list.querySelectorAll('.ep').forEach(el => {{
      el.hidden = f !== 'all' && el.dataset.video !== f;
    }});
  }});
}});
</script>
"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"{OUT} — {len(rows)}회차 (영상 {done}편), {os.path.getsize(OUT) // 1024}KB")


if __name__ == "__main__":
    build()
