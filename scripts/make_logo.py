"""채널 사운드 로고 — 나레이션을 대신해 0.8초로 브랜드를 각인한다.

**왜 만들었나 (2026-09-18).** 유튜브 스튜디오 유지율에서 **7~8초에 30%가 이탈**하는데,
그 자리에 있던 것이 브랜드 나레이션("이름을 부르다. 오늘 부를 이름.") 2.5초 +
무음 1.4초였다. 10편 중 9편이 8초 시점에 이 컷을 재생 중이었다. 훅은 7초까지
사람을 붙잡는 데 성공했는데, 훅이 끝나는 순간 3.9초짜리 정보 공백이 오는 구조였다.

→ 나레이션을 걷어내고 **화면 자막 + 이 사운드 로고**로 대신한다(C안).
채널명이 나오는 위치(초반)는 그대로 두면서 공백만 3.9초 → 0.8초로 줄인다.

소리는 직접 합성한다. 외부 음원은 저작권·Content ID 위험이 있다
(`make_bgm.py`·`impact_fx.py`와 같은 원칙).

**톤 규칙**: 이 채널은 순국을 다룬다. 밝거나 경쾌한 로고는 쓸 수 없다.
낮은 종(鐘) 한 번 — 어택은 부드럽고 꼬리는 길게 남긴다. BGM과 같은 A단조를 쓴다.

    python3 scripts/make_logo.py           # output/audio/locked_takes/logo_bell.wav
    python3 scripts/make_logo.py --preview # 후보 3종을 나란히 뽑아 듣고 고른다
"""
import math
import os
import struct
import sys
import wave

SR = 44100
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(BASE, "output/audio/locked_takes")

# A단조. make_bgm.py의 A_MINOR와 같은 뿌리를 쓴다.
A2, E3, A3 = 110.00, 164.81, 220.00


def _bell(dur, root, partials, decay, attack=0.008):
    """종소리 한 번. 비정수 배음이 섞여야 '땡'이 아니라 '뎅'으로 들린다."""
    n = int(SR * dur)
    out = [0.0] * n
    for i in range(n):
        t = i / SR
        # 빠른 어택 + 긴 지수 감쇠
        env = (1 - math.exp(-t / attack)) * math.exp(-t * decay)
        s = sum(a * math.sin(2 * math.pi * root * r * t) for r, a in partials)
        out[i] = s * env
    return out


def _tail(buf, from_sec, decay=9.0):
    """끝을 눌러 다음 나레이션과 부딪히지 않게 한다."""
    n0 = int(from_sec * SR)
    for i in range(n0, len(buf)):
        buf[i] *= math.exp(-(i - n0) / SR * decay)
    return buf


def _write(path, buf, level=0.5):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    peak = max(1e-9, max(abs(x) for x in buf))
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(
            struct.pack("<h", int(max(-1, min(1, x / peak * level)) * 32767))
            for x in buf))
    return path


def bell_low(dur=0.8):
    """후보 A — 낮은 종 하나. 가장 조용하고 무겁다."""
    buf = _bell(dur, A2, [(1.0, 1.0), (2.0, 0.42), (2.76, 0.22),
                          (5.4, 0.10), (8.9, 0.05)], decay=4.2)
    return _tail(buf, dur - 0.12)


def bell_fifth(dur=0.8):
    """후보 B — 근음 위에 5도를 겹친다. 조금 더 넓고 여운이 길다."""
    a = _bell(dur, A2, [(1.0, 1.0), (2.0, 0.40), (2.76, 0.20), (5.4, 0.09)], decay=4.0)
    b = _bell(dur, E3, [(1.0, 0.55), (2.0, 0.18), (2.76, 0.09)], decay=5.2)
    return _tail([x + y for x, y in zip(a, b)], dur - 0.12)


def bell_two(dur=0.8):
    """후보 C — 두 번 친다(A2 → A3). '이름을' '부르다'의 두 박에 얹힌다."""
    a = _bell(dur, A2, [(1.0, 1.0), (2.0, 0.40), (2.76, 0.20), (5.4, 0.09)], decay=4.6)
    b = _bell(dur, A3, [(1.0, 0.62), (2.0, 0.22), (2.76, 0.11)], decay=5.6)
    off = int(0.26 * SR)
    for i in range(len(b) - off):
        a[off + i] += b[i]
    return _tail(a, dur - 0.12)


CANDIDATES = {"A_low": bell_low, "B_fifth": bell_fifth, "C_two": bell_two}


def main(argv):
    if "--preview" in argv:
        for name, fn in CANDIDATES.items():
            p = _write(os.path.join(OUT, f"_logo_{name}.wav"), fn())
            print(f"  {name:8s} {p}")
        print("\n셋을 들어보고 고른 뒤, 그 함수를 build()에 연결한다.")
        return 0
    p = _write(os.path.join(OUT, "logo_bell.wav"), bell_fifth())
    with wave.open(p) as w:
        print(f"{p}  ({w.getnframes() / w.getframerate():.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
