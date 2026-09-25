"""애국가풍 잔잔한 무가사 BGM — 직접 합성 (2026-09-25 사용자 요청).

남의 음원은 수익창출 영상에서 Content ID가 걸리므로 `make_bgm.py`와 같은 원칙으로 합성한다.
애국가의 선율을 쓰지 않는다(안익태 곡은 국가 기증 저작물이지만, 유튜브 Content ID에
여러 연주 판본이 등록돼 있어 오인 매칭 위험이 있다). **애국가와 같은 느낌**만 만든다:

- 느린 4/4, 장조(G), 찬송가식 4성부 코드 진행 (I–IV–I–V / I–vi–IV–V–I)
- 현악 패드(느린 어택, 살짝 디튠) + 호른 같은 저음 + 단선율(피아노풍 감쇠음)
- 이름 공개 지점에서 부풀었다가(swell) 잔향으로 닫힌다

사용: python3 scripts/make_bgm_anthem.py <초> <이름공개시각> <out.wav>
"""
import math
import sys
import wave

import numpy as np

SR = 44100
BPM = 60                      # 느리게. 한 박 = 1초
BEAT = 60 / BPM

G = 196.00
NOTE = {n: G * 2 ** (i / 12) for i, n in enumerate(
    ["G", "G#", "A", "A#", "B", "C", "C#", "D", "D#", "E", "F", "F#"])}


def hz(name, octave=0):
    return NOTE[name] * 2 ** octave


# 찬송가식 진행 (한 코드 = 2박). 마디 8개 = 16박 = 16초, 반복
PROGRESSION = [
    ("G", ["G", "B", "D"]), ("C", ["C", "E", "G"]), ("G", ["G", "B", "D"]), ("D", ["D", "F#", "A"]),
    ("Em", ["E", "G", "B"]), ("C", ["C", "E", "G"]), ("D", ["D", "F#", "A"]), ("G", ["G", "B", "D"]),
]
# 단선율 — 애국가 선율이 아니라 같은 정서의 상행·하행 (음, 박)
MELODY = [
    ("D", 1, 2), ("E", 1, 1), ("G", 1, 1), ("B", 1, 2), ("A", 1, 1), ("G", 1, 1),
    ("E", 1, 2), ("D", 1, 1), ("E", 1, 1), ("G", 1, 3), (None, 0, 1),
    ("B", 1, 2), ("A", 1, 1), ("B", 1, 1), ("D", 2, 2), ("B", 1, 1), ("A", 1, 1),
    ("G", 1, 2), ("A", 1, 1), ("G", 1, 1), ("D", 1, 3), (None, 0, 1),
]


def env_asr(n, a, r, sr=SR):
    e = np.ones(n)
    na, nr = min(n, int(a * sr)), min(n, int(r * sr))       # 끝에서 잘린 짧은 조각도 안전하게
    if na:
        e[:na] = np.linspace(0, 1, na) ** 2
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr) ** 1.5
    return e


def string_tone(f, n, sr=SR):
    """현악 패드 — 살짝 디튠한 톱니를 겹치고 저역통과 느낌으로 배음을 줄인다."""
    t = np.arange(n) / sr
    out = np.zeros(n)
    for det, amp in ((1.0, 1.0), (1.004, 0.55), (0.996, 0.55), (2.0, 0.18)):
        w = f * det
        # 톱니파의 배음 8개까지만 (부드럽게)
        s = sum(math.sin(0) + np.sin(2 * math.pi * w * k * t) / k for k in range(1, 9))
        out += s * amp
    vib = 1 + 0.004 * np.sin(2 * math.pi * 5.2 * t)          # 아주 얕은 비브라토
    return out * vib / 3.0


def pad_chord(buf, start, dur, notes, amp=0.16):
    n = int(dur * SR)
    n0 = int(start * SR)
    if n0 >= len(buf):
        return
    n = min(n, len(buf) - n0)
    e = env_asr(n, 0.9, 0.9)
    for i, name in enumerate(notes):
        oc = 0 if i else -1                                   # 근음은 한 옥타브 아래
        buf[n0:n0 + n] += string_tone(hz(name, oc), n) * e * amp * (0.9 if i else 1.0)
    # 호른 같은 저음 — 근음 두 옥타브 아래 사인
    t = np.arange(n) / SR
    buf[n0:n0 + n] += np.sin(2 * math.pi * hz(notes[0], -2) * t) * e * amp * 0.5


def piano_note(buf, start, f, dur=2.6, amp=0.22):
    n0 = int(start * SR)
    n = min(int(dur * SR), len(buf) - n0)
    if n <= 0:
        return
    t = np.arange(n) / SR
    env = np.exp(-t * 1.3) * (1 - np.exp(-t * 120))
    s = (np.sin(2 * math.pi * f * t) + 0.35 * np.sin(2 * math.pi * f * 2 * t)
         + 0.12 * np.sin(2 * math.pi * f * 3 * t) + 0.05 * np.sin(2 * math.pi * f * 4 * t))
    buf[n0:n0 + n] += s * env * amp


def swell(buf, at, dur=4.0, amp=0.5):
    """이름 공개 — G 장3화음이 부풀었다 가라앉는다."""
    n0 = max(0, int(at * SR))
    n = min(int(dur * SR), len(buf) - n0)
    if n <= 0:
        return
    t = np.arange(n) / SR
    e = np.sin(math.pi * t / dur) ** 1.4
    for name, oc, a in (("G", -1, 1.0), ("B", 0, 0.6), ("D", 0, 0.7), ("G", 1, 0.35)):
        buf[n0:n0 + n] += string_tone(hz(name, oc), n) * e * amp * a


def reverb(x, sr=SR):
    """짧은 잔향 — 지연 몇 개를 감쇠시켜 더한다."""
    out = x.copy()
    for d, g in ((0.031, 0.30), (0.047, 0.24), (0.071, 0.18), (0.113, 0.12), (0.173, 0.08)):
        k = int(d * sr)
        out[k:] += x[:-k] * g
    return out


def build(total, reveal_at, out):
    buf = np.zeros(int(total * SR))
    # 코드 패드 — 8마디 진행을 곡 길이만큼 반복
    t = 0.0
    while t < total:
        for _, notes in PROGRESSION:
            pad_chord(buf, t, BEAT * 2 + 0.3, notes)
            t += BEAT * 2
            if t >= total:
                break
    # 단선율 — 4박 쉬고 시작, 한 바퀴(22박) 돌고 8박 쉬고 다시
    t = BEAT * 4
    while t < total - 4:
        for name, oc, beats in MELODY:
            if name and t < reveal_at - 1.0:              # 이름 직전부터는 선율을 비운다
                piano_note(buf, t, hz(name, oc), dur=beats * BEAT + 1.2)
            t += beats * BEAT
        t += BEAT * 8
    if reveal_at:
        swell(buf, reveal_at - 0.8)
    buf = reverb(buf)
    # 페이드 인/아웃
    fi, fo = int(2.0 * SR), int(3.0 * SR)
    buf[:fi] *= np.linspace(0, 1, fi) ** 2
    buf[-fo:] *= np.linspace(1, 0, fo) ** 1.5
    buf = buf / (np.max(np.abs(buf)) or 1) * 0.6            # 최종 믹스에서 다시 낮춘다
    with wave.open(out, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((buf * 32767).astype(np.int16).tobytes())
    print(f"saved {out}  ({total:.1f}s, swell {reveal_at:.1f}s)")


if __name__ == "__main__":
    total = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    rev = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    out = sys.argv[3] if len(sys.argv) > 3 else "output/audio/bgm_anthem.wav"
    build(total, rev, out)
