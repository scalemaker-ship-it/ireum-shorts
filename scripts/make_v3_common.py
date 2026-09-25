"""v3 공용 음성 — 모든 회차가 같은 파일을 쓴다 (PRD §28).

    common_v3_phrase.wav    "오늘 우리가 다시 부를 이름."
    common_v3_remember.wav  "오늘, 이 이름 하나만 기억해주세요."

`~세요`는 요청형이라 TTS가 끝음을 올린다(PRD_v2 §2). 그래서 테이크를 여러 개 뽑고
**마지막 음절의 피치가 앞보다 얼마나 내려앉았는지**를 재서 가장 많이 내려간 것을 고른다.
귀로 고르는 것을 대신하는 게 아니라 후보를 좁히는 용도다 — 최종 판단은 들어 보고 한다.

사용:
    python3 scripts/make_v3_common.py            # 둘 다, 테이크 4개씩
    python3 scripts/make_v3_common.py --takes 6
    python3 scripts/make_v3_common.py --force    # 이미 있어도 다시
"""
import argparse
import os
import shutil
import subprocess
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_ending import LOCK, synth_name  # noqa: E402

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LINES = {
    "common_v3_phrase": "오늘 우리가 다시 부를 이름",
    "common_v3_remember": "오늘, 이 이름 하나만 기억해주세요",
    "common_v3_reason": "이 사람을 우리가 기억해야 하는 이유입니다",   # 건축사전 구조 ⑧ (2026-09-25)
    "common_v3_korea": "이런 사람이 있어서 지금의 대한민국이 있습니다",  # 마지막 문장 확정 (2026-09-25 사용자)
    "common_v3_call": "오늘 부를 이름",                                # 이름 앞 호명 문구 (2026-09-25 사용자)
}


def read(p):
    with wave.open(p) as w:
        sr = w.getframerate()
        d = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    return sr, d / 32768.0


def pitch_track(sr, d, win=0.04, hop=0.01):
    """자기상관으로 프레임별 기본주파수. 무성 구간은 NaN."""
    n, h = int(sr * win), int(sr * hop)
    lo, hi = int(sr / 300), int(sr / 70)          # 남성 음역 70~300Hz
    peak = np.max(np.abs(d)) or 1.0
    out = []
    for i in range(0, len(d) - n, h):
        x = d[i:i + n]
        if np.max(np.abs(x)) < peak * 0.08:
            out.append(np.nan)
            continue
        x = x - x.mean()
        ac = np.correlate(x, x, "full")[n - 1:]
        lag = lo + int(np.argmax(ac[lo:hi]))
        out.append(sr / lag if ac[lag] > 0.3 * ac[0] else np.nan)
    return np.array(out)


def end_drop(p):
    """마지막 유성 구간 250ms의 피치 ÷ 그 앞 발화 전체의 중앙값. 작을수록 내려앉았다."""
    sr, d = read(p)
    f0 = pitch_track(sr, d)
    voiced = np.where(~np.isnan(f0))[0]
    if len(voiced) < 30:
        return 9.9
    tail = f0[voiced[-25:]]
    body = f0[voiced[:-25]]
    return float(np.nanmedian(tail) / np.nanmedian(body))


def trim_breath(src, dst):
    """끝 날숨 제거 — 발화 끝 +20ms부터 140ms 페이드 후 절단 (PRD_v2 §8)."""
    sr, d = read(src)
    thr = np.max(np.abs(d)) * 0.05
    idx = np.where(np.abs(d) > thr)[0]
    st = (idx[-1] / sr if len(idx) else len(d) / sr) + 0.02
    subprocess.run(["ffmpeg", "-y", "-i", src, "-af",
                    f"afade=t=out:st={st:.3f}:d=0.14,atrim=0:{st + 0.15:.3f}",
                    "-ar", "44100", "-ac", "1", dst], check=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--takes", type=int, default=4)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    os.makedirs(LOCK, exist_ok=True)
    cand = os.path.join(LOCK, "_v3_candidates")
    os.makedirs(cand, exist_ok=True)

    for key, text in LINES.items():
        final = os.path.join(LOCK, f"{key}.wav")
        if os.path.exists(final) and not a.force:
            print(f"  {key}: 있음 — 건너뜀 (--force로 다시)")
            continue
        scored = []
        for i in range(1, a.takes + 1):
            raw = os.path.join(cand, f"{key}_take{i}.raw.wav")
            synth_name(text, raw)                  # sad 1.4, 마침표로 끝낸다
            clean = os.path.join(cand, f"{key}_take{i}.wav")
            trim_breath(raw, clean)
            s = end_drop(clean)
            scored.append((s, clean))
            print(f"  {key} take{i}: 끝음 비율 {s:.3f}")
        scored.sort()
        shutil.copy(scored[0][1], final)
        print(f"  → {key}: {os.path.basename(scored[0][1])} 채택 (비율 {scored[0][0]:.3f})\n")


if __name__ == "__main__":
    main()
