"""문장 끝의 상승 억양을 눌러 하강조로 바꾼다.

Typecast의 Piljae 보이스는 어절 끝을 살짝 올리는 성향이 있어서, 텍스트나
구두점을 바꿔도 "이름~ 강우규~ 기억해주세요~" 하는 상승 억양이 남는다.
어미를 바꾸는 것으로도 해결되지 않아 신호를 직접 처리한다.

ffmpeg에 rubberband가 없으므로 asetrate + atempo 조합으로 피치만 내린다.
  asetrate=SR*k  → 피치 k배, 길이도 k배
  atempo=1/k     → 길이 원복, 피치만 남음
뒷부분을 여러 조각으로 나눠 조각마다 k를 조금씩 낮추면 자연스러운 하강 램프가 된다.
(한 번에 일정량을 깎으면 경계에서 톤이 뚝 끊기는 게 들린다)
"""
import os
import subprocess
import sys
import tempfile
import wave
import contextlib
import struct

SR = 44100


def dur(path):
    with contextlib.closing(wave.open(path)) as w:
        return w.getnframes() / w.getframerate()


def _seg(src, out, start, length, k=None):
    """구간을 잘라내고, k가 주어지면 길이는 유지한 채 피치만 낮춘다."""
    af = []
    if k is not None and abs(k - 1.0) > 1e-4:
        af = ["-af", f"asetrate={int(SR * k)},aresample={SR},atempo={1 / k:.6f}"]
    subprocess.run(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{length:.3f}",
                    "-i", src, *af, "-ar", str(SR), "-ac", "1", out],
                   check=True, capture_output=True)


def voiced_end(path, rel_thr=0.02):
    """실제 목소리가 끝나는 지점(초).

    TTS 클립은 끝에 0.3~0.5초씩 무음이 붙는다. 파일 끝을 기준으로 처리하면
    그 무음만 건드리고 정작 올라가는 어절 끝은 손대지 못한다.
    """
    with contextlib.closing(wave.open(path)) as w:
        sr, n = w.getframerate(), w.getnframes()
        data = struct.unpack(f"<{n}h", w.readframes(n))
    peak = max(abs(x) for x in data) or 1
    thr = peak * rel_thr
    i = n - 1
    while i > 0 and abs(data[i]) < thr:
        i -= 1
    return i / sr


def fall(src, out, tail=0.75, drop=0.10, steps=6):
    """목소리가 끝나는 지점 기준으로 `tail`초에 걸쳐 피치를 서서히 낮춘다."""
    total = dur(src)
    speech_end = voiced_end(src)
    tail = min(tail, speech_end * 0.9)
    head_len = speech_end - tail

    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        if head_len > 0.02:
            p = os.path.join(tmp, "head.wav")
            _seg(src, p, 0, head_len)
            parts.append(p)

        step_len = tail / steps
        for i in range(steps):
            k = 1.0 - drop * (i + 1) / steps      # 뒤로 갈수록 더 낮게
            p = os.path.join(tmp, f"t{i}.wav")
            _seg(src, p, head_len + i * step_len, step_len, k)
            parts.append(p)

        # 목소리 뒤에 남은 무음은 그대로 붙인다 (처리 대상이 아니다)
        rest = total - speech_end
        if rest > 0.02:
            p = os.path.join(tmp, "rest.wav")
            _seg(src, p, speech_end, rest)
            parts.append(p)

        lst = os.path.join(tmp, "list.txt")
        with open(lst, "w") as f:
            for p in parts:
                f.write(f"file '{p}'\n")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                        "-ar", str(SR), "-ac", "1", out],
                       check=True, capture_output=True)
    return out


if __name__ == "__main__":
    src, out = sys.argv[1], sys.argv[2]
    tail = float(sys.argv[3]) if len(sys.argv) > 3 else 0.75
    drop = float(sys.argv[4]) if len(sys.argv) > 4 else 0.10
    fall(src, out, tail, drop)
    print(f"saved {out}  (tail={tail}s drop={drop})")
