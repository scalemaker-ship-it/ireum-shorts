"""마무리 멘트 조립 — 이름만 바꿔 끼운다.

    오늘 우리가 부른 이름. [이름]. 기억하겠습니다.

앞뒤 두 문장은 **모든 회차가 같은 음성 파일을 재사용**한다. TTS가 비결정적이라
매회 새로 생성하면 마무리 톤이 회차마다 달라지기 때문이다. 회차마다 새로 만드는
것은 가운데 이름 한 마디뿐이다.

사용:
    python3 scripts/make_ending.py 안경신                 # 테이크 1개
    python3 scripts/make_ending.py 안경신 --takes 3       # 3개 뽑아 고르기
    python3 scripts/make_ending.py 안경신 --pick 2 --apply drafts/script_dok_02.json
"""
import argparse
import contextlib
import datetime
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import urllib.request
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_tts import api_key, voice_id, VOICE_NAME, MODEL, API  # noqa: E402

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LOCK = os.path.join(BASE, "output/audio/locked_takes")

HEAD = os.path.join(LOCK, "common_A_head.wav")   # "오늘 우리가 부른 이름." (공용)
TAIL = os.path.join(LOCK, "common_C_tail.wav")   # "기억하겠습니다."        (공용)

PRE_GAP = 0.50        # 유언과 마무리를 분리하는 사이
NAME_GAP = 0.70       # "오늘 우리가 부른 이름." 뒤, 이름을 부르기 전 사이 (사용자 확정)
BEAT_GAP = 0.75       # 이름 뒤 한 템포
NAME_TEMPO = 0.93     # 이름 발음 속도 (1.0보다 느리게)
TARGET_DB = -26.0
TEXTS = ("오늘 우리가 부른 이름.", "{name}.", "기억하겠습니다.")


def dur(p):
    with contextlib.closing(wave.open(p)) as w:
        return w.getnframes() / w.getframerate()


def voiced_end(p, rel=0.02):
    """발화가 끝나는 지점. TTS 뒤에 붙는 무음을 자막 타이밍에서 제외하기 위함."""
    with contextlib.closing(wave.open(p)) as w:
        sr, n = w.getframerate(), w.getnframes()
        d = struct.unpack(f"<{n}h", w.readframes(n))
    thr = (max(abs(x) for x in d) or 1) * rel
    i = n - 1
    while i > 0 and abs(d[i]) < thr:
        i -= 1
    return i / sr


def mean_db(p):
    o = subprocess.run(["ffmpeg", "-i", p, "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    m = re.search(r"mean_volume: (-?[\d.]+)", o)
    return float(m.group(1)) if m else TARGET_DB


def normalize(src, dst):
    """감정 프리셋·테이크마다 레벨이 달라 그대로 이으면 소리가 튄다."""
    subprocess.run(["ffmpeg", "-y", "-i", src, "-af", f"volume={TARGET_DB - mean_db(src):+.2f}dB",
                    "-ar", "44100", "-ac", "1", dst], check=True, capture_output=True)
    return dst


def silence(sec, dst):
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-t", str(sec),
                    "-i", "anullsrc=r=44100:cl=mono", dst], check=True, capture_output=True)
    return dst


def synth_name(name, dst, punct="."):
    """이름 한 마디. 본문(tonedown)과 달리 마무리는 sad 1.4로 간다.

    끝음을 낮추려고 피치를 건드린 적이 있는데 '늘어진다'는 지적을 받고 뺐다.
    지금은 신호처리를 하지 않고 감정 프리셋과 **문장부호**로만 억양을 잡는다.
    """
    body = {"voice_id": voice_id(api_key(), VOICE_NAME), "text": f"{name}{punct}",
            "model": MODEL, "speed": 0.95,
            "prompt": {"emotion_preset": "sad", "emotion_intensity": 1.4},
            "output": {"audio_format": "wav"}}
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "X-API-KEY": api_key()})
    with urllib.request.urlopen(req) as resp, open(dst, "wb") as f:
        f.write(resp.read())
    return dst


def assemble(name_wav, out_wav, tmp, name_gap=NAME_GAP, tail_src=None):
    """[사이] 이름문장 → [사이] → 인명 → [사이] → 기억하겠습니다 순으로 잇는다.

    이름을 부르기 직전의 사이(name_gap)가 이 시리즈에서 가장 중요한 한 박이다.
    붙여 읽으면 이름이 문장에 묻힌다.
    """
    pre = silence(PRE_GAP, os.path.join(tmp, "_pre.wav"))
    gap = silence(name_gap, os.path.join(tmp, "_gap.wav"))
    beat = silence(BEAT_GAP, os.path.join(tmp, "_beat.wav"))
    head = normalize(HEAD, os.path.join(tmp, "_head.wav"))
    tail = normalize(tail_src or TAIL, os.path.join(tmp, "_tail.wav"))
    parts = [pre, head, gap, name_wav, beat, tail]

    lst = os.path.join(tmp, "_list.txt")
    with open(lst, "w") as f:
        for p in parts:
            f.write(f"file '{os.path.abspath(p)}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-ar", "44100", "-ac", "1", out_wav], check=True, capture_output=True)

    d = [dur(p) for p in parts]
    total = sum(d)
    # t[i] = parts[i+1]이 시작하는 시각
    t, acc = [], 0.0
    for x in d[:-1]:
        acc += x
        t.append(acc)
    voice_end = t[4] + voiced_end(tail)
    return total, t, voice_end


def schedule(name, total, t, voice_end):
    """자막 노출 스케줄. 사이 구간에는 자막이 멈춰 있어야 한다.

    글자 수는 반드시 **줄바꿈된 결과**에서 세야 한다. 줄이 넘어갈 때 공백이
    사라지므로 원문 길이로 계산하면 build_episode의 reveal 기준과 어긋난다.
    """
    from archive_layout import caption_lines, load, NOTO_SERIF  # 지연 임포트

    texts = [TEXTS[0], TEXTS[1].format(name=name), TEXTS[2]]
    full = " ".join(texts)
    joined = "".join(caption_lines(full, load(NOTO_SERIF, 46, weight=400)))

    # 문장 끝 마침표 위치로 누적 글자 수를 잡는다
    p1 = joined.find(".") + 1
    p2 = joined.find(".", p1) + 1
    c1, c2, c3 = p1, p2, len(joined)

    return full, [
        [round(t[0] / total, 4), 0],       # 앞 사이 — 자막 없음
        [round(t[1] / total, 4), c1],      # "오늘 우리가 부른 이름." 완성
        [round(t[2] / total, 4), c1],      # 이름 앞 사이 — 멈춤
        [round(t[3] / total, 4), c2],      # 이름까지
        [round(t[4] / total, 4), c2],      # 이름 뒤 사이 — 멈춤
        [round(voice_end / total, 4), c3],
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--takes", type=int, default=1)
    ap.add_argument("--pick", type=int, help="이미 뽑아둔 테이크 번호로 확정")
    ap.add_argument("--apply", help="확정 결과를 반영할 대본 JSON 경로")
    ap.add_argument("--slug", default=None, help="파일명에 쓸 영문 약칭")
    ap.add_argument("--name-gap", type=float, default=NAME_GAP,
                    help="이름을 부르기 전 사이(초). 같은 이름 테이크로 사이만 바꿔 비교할 때 쓴다")
    a = ap.parse_args()

    slug = a.slug or "ep"
    tmp = os.path.join(BASE, "output/audio/_ending_tmp")
    os.makedirs(tmp, exist_ok=True)
    outdir = os.path.join(BASE, "output/audio/endings")
    os.makedirs(outdir, exist_ok=True)

    from name_from_carrier import main as carrier_name   # 지연 임포트

    for i in range(1, a.takes + 1):
        # 이름은 **캐리어 문장에서 잘라낸다.** 단독 합성하면 호명하듯 읽어 끝음이 뜨는데,
        # 본문 06번("...그의 이름은, OOO.")과 억양이 달라 보인다는 지적을 받았다.
        # ⚠️ 파일명에 **인물 이름을 반드시 넣는다.** 예전에는 `name{i}.wav`라는
        # 고정 경로였는데, `--pick`을 주면 "이미 있으면 다시 합성하지 않는다"는
        # 분기와 맞물려 **앞 회차의 이름 음성이 그대로 재사용됐다.**
        # 실제로 11화(조명하) 엔딩에 10화(이육사) 목소리가 들어가 렌더까지 마쳤다
        # (2026-09-18). 캐시의 목적은 "같은 인물의 테이크를 다시 조립할 때"이지
        # 인물을 건너뛰는 것이 아니다.
        sped = os.path.join(tmp, f"name_{a.name}_{i}.wav")
        if a.pick is not None and i != a.pick:
            continue
        if os.path.exists(sped):
            print(f"  ⚠️ 캐시 재사용: {os.path.basename(sped)} "
                  f"({datetime.datetime.fromtimestamp(os.path.getmtime(sped)):%m-%d %H:%M} 생성)")
        else:
            carrier_name(a.name, sped)
        normalize(sped, sped + ".n.wav")

        tag = f"take{i}" if a.name_gap == NAME_GAP else f"take{i}_gap{a.name_gap:.2f}"
        out = os.path.join(outdir, f"{slug}_ending_{tag}.wav")
        total, t, ve = assemble(sped + ".n.wav", out, tmp, a.name_gap)

        # 마지막 안전장치 — 다른 회차 엔딩과 바이트가 같으면 이름이 잘못 들어간 것이다.
        # 앞뒤 문장이 공용 파일이라 **이름만 틀려도 귀로는 놓치기 쉽다.** 숫자로 막는다.
        mine = hashlib.md5(open(out, "rb").read()).hexdigest()
        for f in sorted(os.listdir(outdir)):
            p = os.path.join(outdir, f)
            if p == out or not f.endswith(".wav"):
                continue
            if hashlib.md5(open(p, "rb").read()).hexdigest() == mine:
                os.remove(out)
                raise SystemExit(
                    f"❌ 생성된 엔딩이 {f}와 완전히 같습니다 — 이름 음성이 재사용된 것입니다.\n"
                    f"   {os.path.basename(sped)}를 지우고 다시 실행하세요.")
        text, sched = schedule(a.name, total, t, ve)
        print(f"  take{i}: {total:.2f}s  →  {out}")

        if a.apply and (a.pick == i or a.takes == 1):
            p = os.path.join(BASE, a.apply) if not os.path.isabs(a.apply) else a.apply
            s = json.load(open(p, encoding="utf-8"))
            for seg in s["segments"]:
                if seg["id"] == "09_cta":
                    seg["text"] = text
                    seg["locked_audio"] = os.path.relpath(out, BASE)
                    seg["reveal_points"] = sched
            json.dump(s, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print(f"  대본 반영: {a.apply}")
            print(f"    text = {text}")
            print(f"    reveal_points = {sched}")


if __name__ == "__main__":
    main()
