"""'이름을 부르다' 시리즈 BGM 생성기.

외부 음원을 쓰지 않고 직접 합성한다. 수익창출 영상에 남의 음원을 쓰면
라이선스 확인 부담이 크고, 잘못 쓰면 저작권 클레임으로 수익이 넘어간다.
합성물은 그 위험이 0이다.

구성: 낮은 드론(지속음) + 드문드문 떨어지는 피아노풍 단음.
나레이션을 방해하지 않도록 아주 낮은 레벨로 깐다.
"""
import math
import struct
import sys
import wave

SR = 44100
A_MINOR = [220.00, 261.63, 293.66, 329.63, 392.00, 440.00, 523.25]  # A단조 음계


def _env_drone(t, dur, fade=4.0):
    """드론 전체 페이드 인/아웃."""
    if t < fade:
        return t / fade
    if t > dur - fade:
        return max(0.0, (dur - t) / fade)
    return 1.0


def drone(dur, root=110.0):
    """근음 + 5도 + 옥타브를 아주 살짝 디튠해 겹친다 (맥놀이로 두께를 만든다)."""
    out = [0.0] * int(dur * SR)
    partials = [(root, 1.00), (root * 1.5, 0.42), (root * 2, 0.24),
                (root * 1.002, 0.55), (root * 0.999, 0.5)]
    for i in range(len(out)):
        t = i / SR
        # 아주 느린 음량 흔들림 — 숨 쉬는 느낌
        lfo = 0.82 + 0.18 * math.sin(2 * math.pi * 0.045 * t)
        s = sum(a * math.sin(2 * math.pi * f * t) for f, a in partials)
        out[i] = s * lfo * _env_drone(t, dur)
    return out


def note(buf, start, freq, dur=3.2, amp=0.5):
    """감쇠하는 단음. 배음을 얹어 피아노에 가깝게."""
    n0 = int(start * SR)
    for i in range(int(dur * SR)):
        if n0 + i >= len(buf):
            break
        t = i / SR
        env = math.exp(-t * 1.15) * (1 - math.exp(-t * 90))   # 빠른 어택, 긴 감쇠
        s = (math.sin(2 * math.pi * freq * t)
             + 0.30 * math.sin(2 * math.pi * freq * 2 * t)
             + 0.12 * math.sin(2 * math.pi * freq * 3 * t))
        buf[n0 + i] += s * env * amp


def swell(buf, at, dur=3.0, amp=0.9, freq=164.81):
    """반전 지점 스팅 — 낮은 음이 부풀었다 가라앉는다."""
    n0 = int(at * SR)
    for i in range(int(dur * SR)):
        if n0 + i >= len(buf):
            break
        t = i / SR
        p = t / dur
        env = math.sin(math.pi * p) ** 1.6
        s = (math.sin(2 * math.pi * freq * t)
             + 0.5 * math.sin(2 * math.pi * freq * 1.5 * t)
             + 0.25 * math.sin(2 * math.pi * freq * 2 * t))
        buf[n0 + i] += s * env * amp


def build(dur, reveal_at=None, out="bgm.wav", level=0.055):
    buf = drone(dur)

    # 드문드문 떨어지는 단음 — 규칙적이지 않게
    pattern = [(2.0, 3), (9.5, 0), (16.0, 4), (23.0, 2), (31.0, 0),
               (38.5, 3), (46.0, 1), (52.0, 0)]
    for at, deg in pattern:
        if at < dur - 1:
            note(buf, at, A_MINOR[deg] * 2, amp=0.18)

    if reveal_at:
        swell(buf, max(0, reveal_at - 0.6))

    peak = max(abs(x) for x in buf) or 1.0
    scale = level / peak

    with wave.open(out, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, x * scale)) * 32767)) for x in buf))
    print(f"saved {out}  ({dur:.1f}s)")


if __name__ == "__main__":
    total = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    reveal = float(sys.argv[2]) if len(sys.argv) > 2 else None
    out = sys.argv[3] if len(sys.argv) > 3 else "output/audio/bgm.wav"
    build(total, reveal, out)
