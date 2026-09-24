"""어절 끝에 끌리는 꼬리를 잘라낸다.

Piljae 보이스는 마지막 음절을 길게 끌면서 억양을 올린다. 그 꼬리 자체를
없애면 상승이 사라진다.

피치를 내리는 방식(pitch_fall.py)도 시도했으나, asetrate/atempo 리샘플링이
섞여 오히려 늘어지게 들렸다. 여기서는 신호를 변형하지 않고 잘라내기만 한다.
"""
import contextlib
import os
import struct
import sys
import wave

SR = 44100


def read(path):
    with contextlib.closing(wave.open(path)) as w:
        n = w.getnframes()
        return list(struct.unpack(f"<{n}h", w.readframes(n))), w.getframerate()


def write(path, data, sr=SR):
    with wave.open(path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(max(-32768, min(32767, x))))
                               for x in data))


def voiced_end(data, rel_thr=0.02):
    peak = max(abs(x) for x in data) or 1
    thr = peak * rel_thr
    i = len(data) - 1
    while i > 0 and abs(data[i]) < thr:
        i -= 1
    return i


def trim(src, out, cut=0.18, fade=0.07, pad=0.25):
    """목소리 끝에서 `cut`초를 잘라내고 `fade`초로 부드럽게 닫는다.

    cut  : 끌리는 꼬리를 얼마나 없앨지
    fade : 자른 자리에서 딸깍 소리가 나지 않게 감쇠
    pad  : 뒤에 남길 무음
    """
    data, sr = read(src)
    end = voiced_end(data)
    keep = max(int(sr * 0.2), end - int(sr * cut))

    out_buf = data[:keep]
    f = min(int(sr * fade), len(out_buf))
    for i in range(f):                       # 끝을 매끄럽게 닫는다
        out_buf[keep - f + i] = int(out_buf[keep - f + i] * (1 - i / f))
    out_buf += [0] * int(sr * pad)

    write(out, out_buf, sr)
    return len(out_buf) / sr


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    cut = float(sys.argv[3]) if len(sys.argv) > 3 else 0.18
    print(f"{trim(src, dst, cut):.2f}s -> {dst}")
