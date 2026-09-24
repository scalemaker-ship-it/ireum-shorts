"""업로드 정보(제목·설명란·태그·고정 댓글)를 대본 JSON에서 만든다.

한 곳에서만 만들어야 대본집 페이지와 `drafts/upload_*.md`가 어긋나지 않는다.

⚠️ **설명란에 URL을 쓰지 않는다** (2026-09-14 사용자 지시).
출처는 기관명·자료명까지만 남긴다. 근거를 밝히는 목적은 그것으로 충족되고,
링크가 길게 늘어지면 설명란 앞부분이 밀려 정작 읽혀야 할 줄이 접힌다.
전체 URL은 대본 JSON의 `sources`와 대본집 '검증 기록'에 그대로 남아 있다.

⚠️ **해시태그 순서를 바꾸지 말 것.** 유튜브는 설명란의 앞 3개를 제목 위로 올린다.
인물 이름은 반드시 4번째 이후여야 반전이 깨지지 않는다.

## 검색 유입 설계 (2026-09-21)

사용자 요청 — "숏츠가 검색으로도 유입됐으면 좋겠다".
⚠️ **이 채널의 포맷과 검색은 상충한다.** 인물명을 제목에 넣어야 그 이름으로 검색되는데,
이 채널은 이름을 마지막까지 숨긴다. 그래서 **층을 나눈다**:

| 자리 | 넣는 것 | 이유 |
|---|---|---|
| 제목 | 소제목 + **범주 해시태그 1개** | 이름은 못 넣는다. 대신 검색량이 있는 범주어를 잡는다 |
| 설명 첫 줄 | 연도·지역·사건 키워드 | 검색 스니펫에 노출되는 자리 |
| 설명 하단 | 인물명·서훈 | 기존대로 '※ 아래에 이름이 있습니다' 뒤 |
| 태그 | 인물명 포함 전부 | 화면에 안 보이므로 반전이 깨지지 않는다 |

**'조명하' 같은 개별 인물명의 검색량은 거의 없다.** 실익은 '독립운동가·일제강점기·한국사'
같은 범주어와 '대만 의거' 같은 롱테일에 있다. 그래서 제목을 이름으로 채우는 대신
범주어를 붙이는 쪽이 포맷도 지키고 유입도 잡는다.

⚠️ **수동 자막(SRT)은 만들지 않기로 했다(2026-09-21).** 한때 검색 색인을 노려
`make_srt.py`를 만들었으나, **유튜브는 자동 생성 자막을 이미 인덱싱한다.**
수동 자막의 실익은 고유명사 정확도뿐인데, 개별 인물명의 검색량 자체가 거의 없어
들이는 품에 비해 얻는 것이 없다. 사용자 판단으로 철회.

⚠️ **제목의 해시태그는 1개만.** 유튜브는 제목에 태그가 3개를 넘으면 전부 무시한다.
"""
import re

HEAD = ("독립운동가 한 사람의 이야기를 1분에 담습니다. 이름은 마지막에 부릅니다.\n"
        "다음에 부르고 싶은 이름을 댓글로 남겨 주세요.")
RULE = "──────────────\n※ 아래에 이 편 인물의 이름이 있습니다."
PINNED = "다음에 부르고 싶은 이름을 댓글로 남겨주세요."
BASE_HASH = ["독립운동가", "한국사", "근현대사"]      # 이 셋이 제목 위로 올라간다
TITLE_HASH = "독립운동가"                              # 제목에 붙이는 태그. 1개만.
# 전 회차 공통 태그. 개별 회차 태그(인물명·사건명)는 대본 upload.tags에 둔다.
COMMON_TAGS = ["독립운동가", "한국사", "근현대사", "역사", "일제강점기",
               "항일운동", "독립운동", "순국선열", "한국사shorts", "역사shorts"]


def strip_url(src):
    """'기관명 자료명 https://...' → '기관명 자료명'."""
    return re.sub(r"\s*https?://\S+", "", src).strip(" ·-—")


def photo_line(credit):
    """크레딧 줄에서 사진 출처만 뽑는다. 미확보 회차는 그 사실을 적는다."""
    for c in credit or []:
        if c.startswith("전하는 사진이"):
            return "· 초상: 전하는 사진이 확인되지 않아 빈 인화지로 두었습니다"
        # ⚠️ '사진 ·'만 보다가 14화(채용신 초상화)의 '그림 ·'을 놓쳐
        #    설명란에서 초상 출처가 통째로 빠진 적이 있다(2026-09-21).
        #    공공누리는 출처표시가 이용 조건이므로 설명란에 반드시 실려야 한다.
        if c.startswith("사진 ·") or c.startswith("그림 ·"):
            return "· 초상: " + c.split("·", 1)[1].strip()
    return ""


def build(script):
    up = script.get("upload") or {}
    title = script["display_title"]
    name = (script.get("nameplate") or [""])[0]

    # 검색 스니펫에 잡히는 자리. 연도·지역·사건을 여기서 먼저 준다.
    # ⚠️ 인물명은 넣지 않는다 — 이 줄은 설명란 맨 위라 접히기 전에 보인다.
    lede = up.get("lede")

    lines = [title, ""]
    if lede:
        lines += [lede, ""]
    lines += [HEAD, "", RULE, "",
              f"인물: {script['subject']}",
              f"서훈: {script['award']}", "", "출처"]
    lines += [f"· {strip_url(s)}" for s in script.get("sources", [])]
    ph = photo_line(script.get("credit"))
    if ph:
        lines.append(ph)

    # 해시태그에 공백이 들어가면 거기서 잘린다 ('#프랭크 스코필드' → '#프랭크')
    tail = up.get("hashtags_extra") or []
    tags = [h.replace(" ", "") for h in BASE_HASH + [name] + tail]
    lines += ["", " ".join("#" + h for h in tags)]

    # 개별 태그(인물명·사건명)를 앞에 두고 공통 태그로 채운다. 중복은 순서를 지켜 지운다.
    tags, seen = [], set()
    for t in list(up.get("tags", [])) + COMMON_TAGS + ["shorts"]:
        if t not in seen:
            seen.add(t)
            tags.append(t)

    return {
        "title": f"{title} #{TITLE_HASH} #shorts",
        "description": "\n".join(lines),
        "tags": tags,
        "playlists": up.get("playlists", []),
        "pinned": PINNED,
        "settings": ["시청자층: 아동용 아님",
                     "AI 콘텐츠 고지: 아니요 — 실존 인물의 얼굴·음성을 합성하지 않음",
                     "댓글: 허용 / 부적절할 수 있는 단어 보류 ON"],
    }


def to_markdown(script, video_path=None, secs=None):
    u = build(script)
    n = script["episode"]
    head = f"# {n}화 업로드 양식 — {(script.get('nameplate') or [''])[0]}\n"
    if video_path:
        head += f"\n**파일**: `{video_path}`" + (f" ({secs:.0f}초)" if secs else "") + "\n"
    blocks = [head,
              "## 제목\n```\n" + u["title"] + "\n```",
              "## 설명란\n```\n" + u["description"] + "\n```",
              "> 해시태그 순서 고정 — 유튜브가 앞 3개를 제목 위로 올린다. "
              "인물 이름은 반드시 4번째 이후.",
              "## 태그\n```\n" + ", ".join(u["tags"]) + "\n```",
              "## 고정 댓글 (업로드 후 직접 고정)\n```\n" + u["pinned"] + "\n```",
              "## 재생목록\n" + "\n".join(f"- {p}" for p in u["playlists"]),
              "## 업로드 설정\n" + "\n".join(f"- [ ] {s}" for s in u["settings"])]
    return "\n\n".join(blocks) + "\n"
