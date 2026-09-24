"""사건 순간의 소리와 흔들림.

폭발·총성이 나오는 컷에서 **나레이션 앞에 소리를 먼저 두고 화면을 흔든다.**
소리는 직접 합성한다 — 효과음 파일을 받아 쓰면 저작권과 Content ID가 걸린다.

⚠️ **아껴 쓴다.** 이 채널은 순국을 다루므로 소리가 흔하면 액션 편집처럼 보인다.
회차당 한 번, 사건이 실제로 일어나는 컷에만 넣는다. 추모 컷에는 절대 넣지 않는다.
날카로운 '빵'이 아니라 **멀리서 둔하게 울리는** 소리를 쓴다.
"""
import math
import os
import random
import struct
import subprocess
import wave

SR = 44100


def _write(path, samples):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        peak = max(1e-9, max(abs(x) for x in samples))
        w.writeframes(b"".join(
            struct.pack("<h", int(max(-1, min(1, x / peak * 0.86)) * 32767))
            for x in samples))
    return path


def _lowpass(xs, a=0.06):
    out, y = [], 0.0
    for x in xs:
        y += a * (x - y)
        out.append(y)
    return out


def explosion(path, dur=1.9, seed=3):
    """둔하게 울리는 폭발음. 저역 충격 + 걸러낸 잡음 + 긴 잔향."""
    rnd = random.Random(seed)
    n = int(SR * dur)
    noise = _lowpass([rnd.uniform(-1, 1) for _ in range(n)], 0.035)
    out = []
    for i in range(n):
        t = i / SR
        env = math.exp(-t * 2.6)                      # 빠르게 떨어지고 길게 남는다
        thump = math.sin(2 * math.pi * 42 * t) * math.exp(-t * 7.0) * 0.9
        sub = math.sin(2 * math.pi * 26 * t) * math.exp(-t * 3.2) * 0.6
        out.append((noise[i] * 1.6 + thump + sub) * env)
    # 앞 12ms 페이드인 — 클릭 방지
    for i in range(int(SR * 0.012)):
        out[i] *= i / (SR * 0.012)
    return _write(path, out)


def gunshot(path, dur=1.2, seed=5):
    """멀리서 들리는 총성. 짧은 파열 + 울림."""
    rnd = random.Random(seed)
    n = int(SR * dur)
    noise = _lowpass([rnd.uniform(-1, 1) for _ in range(n)], 0.10)
    out = []
    for i in range(n):
        t = i / SR
        crack = noise[i] * math.exp(-t * 26)
        tail = _ = math.sin(2 * math.pi * 68 * t) * math.exp(-t * 4.0) * 0.35
        room = noise[i] * math.exp(-t * 3.0) * 0.25
        out.append(crack + tail + room)
    for i in range(int(SR * 0.004)):
        out[i] *= i / (SR * 0.004)
    return _write(path, out)


def shake(t, frames, amp=16, decay=7.0, seed=11):
    """진행도 t(0~1)에서의 화면 흔들림 오프셋 (dx, dy).

    소리가 난 직후 짧게 크게 떨리고 빠르게 가라앉는다. 오래 흔들면 멀미가 난다.
    """
    if t <= 0:
        return (0, 0)
    rnd = random.Random(seed + int(t * frames))
    k = math.exp(-t * decay)
    a = amp * k
    return (int(rnd.uniform(-a, a)), int(rnd.uniform(-a * 0.7, a * 0.7)))


def sentence_end(voice_wav, nth=1, gap_ms=120, rel=0.05):
    """nth번째 문장이 끝나는 시각. TTS가 마침표마다 넣는 사이로 찾는다."""
    with wave.open(voice_wav) as w:
        sr, n = w.getframerate(), w.getnframes()
        d = struct.unpack(f"<{n}h", w.readframes(n))
    win = int(sr * 0.01)
    env = [max(abs(x) for x in d[i:i + win]) or 0 for i in range(0, len(d) - win, win)]
    thr = max(env) * rel
    voiced = [e > thr for e in env]
    runs, i = [], 0
    while i < len(voiced):
        if not voiced[i]:
            j = i
            while j < len(voiced) and not voiced[j]:
                j += 1
            if (j - i) * 10 >= gap_ms and i > 0 and j < len(voiced):
                runs.append(i * win / sr)      # 사이가 '시작되는' 지점 = 말이 끝난 지점
            i = j
        else:
            i += 1
    if not runs:
        return None
    return runs[min(nth - 1, len(runs) - 1)]


def overlay(sfx_wav, voice_wav, out_wav, at, sfx_db=-8.0):
    """효과음을 나레이션 **안쪽 지정 지점**에 얹는다. 길이는 늘어나지 않는다.

    소리를 앞에 두면 맥락 없는 굉음이 된다. 문장이 사건을 말하는 순간
    ("…폭탄이 터졌다")에 맞춰 얹어야 효과음이 아니라 문장의 일부가 된다.
    """
    subprocess.run([
        "ffmpeg", "-y", "-i", voice_wav, "-i", sfx_wav,
        "-filter_complex",
        f"[1:a]volume={sfx_db}dB,adelay={int(at * 1000)}|{int(at * 1000)}[s];"
        "[0:a][s]amix=inputs=2:duration=first:normalize=0[a]",
        "-map", "[a]", "-ar", "44100", "-ac", "1", out_wav,
    ], check=True, capture_output=True)
    return out_wav


def prepend(sfx_wav, voice_wav, out_wav, lead=0.85, sfx_db=-8.0):
    """효과음을 나레이션 앞에 붙인다 (소리가 먼저, 말이 나중).

    맥락 없이 큰 소리부터 나가므로 되도록 overlay()를 쓴다.
    """
    subprocess.run([
        "ffmpeg", "-y", "-i", sfx_wav, "-i", voice_wav,
        "-filter_complex",
        f"[0:a]volume={sfx_db}dB,adelay=0|0[s];"
        f"[1:a]adelay={int(lead * 1000)}|{int(lead * 1000)}[v];"
        "[s][v]amix=inputs=2:duration=longest:normalize=0[a]",
        "-map", "[a]", "-ar", "44100", "-ac", "1", out_wav,
    ], check=True, capture_output=True)
    return out_wav
