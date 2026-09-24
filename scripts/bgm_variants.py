"""BGM 후보 생성 — 결이 다른 네 가지를 같은 길이로 뽑아 비교한다.

전부 직접 합성한다. 남의 음원을 쓰면 수익창출 시 저작권 클레임 위험이 있다.
"""
import math
import os
import random
import struct
import sys
import wave

SR = 44100

# 음계 (Hz)
A_MIN = [220.00, 246.94, 261.63, 293.66, 329.63, 349.23, 392.00, 440.00]   # 가단조
D_MIN = [146.83, 164.81, 174.61, 196.00, 220.00, 233.08, 261.63, 293.66]   # 라단조
PENTA = [220.00, 261.63, 293.66, 329.63, 392.00, 440.00, 523.25]           # 5음계(동양적)


def _fade(t, dur, f=3.5):
    if t < f:
        return t / f
    if t > dur - f:
        return max(0.0, (dur - t) / f)
    return 1.0


def drone(buf, dur, root, amp=1.0, lfo_hz=0.045):
    parts = [(root, 1.0), (root * 1.5, 0.4), (root * 2, 0.22),
             (root * 1.002, 0.5), (root * 0.998, 0.45)]
    for i in range(len(buf)):
        t = i / SR
        lfo = 0.82 + 0.18 * math.sin(2 * math.pi * lfo_hz * t)
        buf[i] += sum(a * math.sin(2 * math.pi * f * t) for f, a in parts) \
            * lfo * _fade(t, dur) * amp


def pluck(buf, start, freq, dur=3.2, amp=0.5, decay=1.15, bright=1.0):
    n0 = int(start * SR)
    for i in range(int(dur * SR)):
        if n0 + i >= len(buf):
            break
        t = i / SR
        env = math.exp(-t * decay) * (1 - math.exp(-t * 90))
        s = (math.sin(2 * math.pi * freq * t)
             + 0.30 * bright * math.sin(2 * math.pi * freq * 2 * t)
             + 0.12 * bright * math.sin(2 * math.pi * freq * 3 * t))
        buf[n0 + i] += s * env * amp


def bowed(buf, start, freq, dur=5.0, amp=0.4):
    """현악처럼 서서히 부풀었다 사라지는 지속음."""
    n0 = int(start * SR)
    for i in range(int(dur * SR)):
        if n0 + i >= len(buf):
            break
        t = i / SR
        env = math.sin(math.pi * (t / dur)) ** 1.4
        vib = 1 + 0.004 * math.sin(2 * math.pi * 5.2 * t)
        s = (math.sin(2 * math.pi * freq * vib * t)
             + 0.45 * math.sin(2 * math.pi * freq * 2 * vib * t)
             + 0.2 * math.sin(2 * math.pi * freq * 3 * vib * t))
        buf[n0 + i] += s * env * amp


def heartbeat(buf, dur, bpm=46, amp=0.55):
    """낮은 북 — 긴장을 아주 느리게 끌고 간다."""
    step = 60.0 / bpm
    t = 1.0
    while t < dur - 1:
        for off, a in ((0.0, 1.0), (0.28, 0.6)):
            n0 = int((t + off) * SR)
            for i in range(int(0.5 * SR)):
                if n0 + i >= len(buf):
                    break
                x = i / SR
                env = math.exp(-x * 9)
                buf[n0 + i] += math.sin(2 * math.pi * 52 * x) * env * amp * a
        t += step


def swell(buf, at, dur=3.0, amp=0.9, freq=164.81):
    n0 = int(at * SR)
    for i in range(int(dur * SR)):
        if n0 + i >= len(buf):
            break
        t = i / SR
        env = math.sin(math.pi * (t / dur)) ** 1.6
        s = (math.sin(2 * math.pi * freq * t)
             + 0.5 * math.sin(2 * math.pi * freq * 1.5 * t)
             + 0.25 * math.sin(2 * math.pi * freq * 2 * t))
        buf[n0 + i] += s * env * amp


def save(buf, out, level=0.055):
    peak = max(abs(x) for x in buf) or 1.0
    k = level / peak
    with wave.open(out, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(b"".join(
            struct.pack("<h", int(max(-1, min(1, x * k)) * 32767)) for x in buf))
    print("saved", out)


def v1_current(dur, reveal):
    """현재 것 — 드론 + 드문드문 단음."""
    buf = [0.0] * int(dur * SR)
    drone(buf, dur, 110.0)
    for at, deg in [(2, 3), (9.5, 0), (16, 4), (23, 2), (31, 0), (38.5, 3), (46, 1), (52, 0)]:
        if at < dur - 1:
            pluck(buf, at, A_MIN[deg] * 2, amp=0.34)
    swell(buf, max(0, reveal - 0.6))
    return buf


def v2_strings(dur, reveal):
    """현악 중심 — 애도하는 느낌, 단음 없이 지속음만."""
    buf = [0.0] * int(dur * SR)
    drone(buf, dur, 98.0, amp=0.7, lfo_hz=0.03)
    prog = [(0, 4), (11, 2), (22, 5), (33, 1), (44, 3)]
    for at, deg in prog:
        if at < dur - 2:
            bowed(buf, at, D_MIN[deg], dur=min(9.0, dur - at), amp=0.42)
            bowed(buf, at, D_MIN[deg] * 1.5, dur=min(9.0, dur - at), amp=0.18)
    swell(buf, max(0, reveal - 0.6), amp=1.0)
    return buf


def v3_pulse(dur, reveal):
    """낮은 북 — 추적당하는 긴장. 사건 전개형."""
    buf = [0.0] * int(dur * SR)
    drone(buf, dur, 87.31, amp=0.55, lfo_hz=0.06)
    heartbeat(buf, dur)
    for at, deg in [(6, 0), (18, 2), (30, 0), (42, 4)]:
        if at < dur - 1:
            pluck(buf, at, D_MIN[deg] * 2, amp=0.26, decay=1.6)
    swell(buf, max(0, reveal - 0.6), amp=1.1)
    return buf


def v4_sparse(dur, reveal):
    """5음계 단음 위주 — 여백이 많고 동양적. 드론은 아주 옅게."""
    buf = [0.0] * int(dur * SR)
    drone(buf, dur, 110.0, amp=0.3, lfo_hz=0.035)
    rnd = random.Random(11)
    t = 1.5
    while t < dur - 2:
        deg = rnd.choice([0, 1, 2, 4, 5])
        pluck(buf, t, PENTA[deg] * 2, dur=4.5, amp=0.42, decay=0.85, bright=0.7)
        t += rnd.uniform(3.4, 6.2)
    swell(buf, max(0, reveal - 0.6), amp=0.8)
    return buf


if __name__ == "__main__":
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 57.4
    reveal = float(sys.argv[2]) if len(sys.argv) > 2 else 36.4
    out_dir = "output/audio/bgm_candidates"
    os.makedirs(out_dir, exist_ok=True)
    for name, fn in [("V1_현재_드론", v1_current), ("V2_현악_애도", v2_strings),
                     ("V3_북_긴장", v3_pulse), ("V4_5음계_여백", v4_sparse)]:
        save(fn(dur, reveal), f"{out_dir}/{name}.wav")
