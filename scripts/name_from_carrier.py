"""마무리에 쓸 이름 한 마디를 '문장 속 억양'으로 뽑는다.

이름만 단독으로 합성하면 TTS가 호명하듯 읽어 끝음이 뜬다. 본문 06번
("...그의 이름은, 안경신.")에서는 문장 끝이라 자연스럽게 내려앉는데,
마무리는 단독 합성이라 억양이 달라 보였다.

그래서 같은 캐리어 문장을 본문과 **같은 설정**(tonedown, 배속 1.15)으로 합성한 뒤
마지막 묵음 뒤의 이름 부분만 잘라 쓴다.
"""
import contextlib, os, struct, subprocess, sys, wave
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_tts import synth, api_key, voice_id, VOICE_NAME  # noqa: E402

BODY_TEMPO = 1.15          # build_episode.py의 SPEED와 같아야 한다
CARRIER = "그의 이름은, {name}."


def read(path):
    with contextlib.closing(wave.open(path)) as w:
        sr, n = w.getframerate(), w.getnframes()
        return sr, list(struct.unpack(f"<{n}h", w.readframes(n)))


def last_word_start(path, gap_ms=50, rel=0.06):
    """쉼표 뒤 마지막 토막이 시작하는 지점.

    처음엔 '뒤에서부터 140ms 이상 묵음을 찾는다'로 짰는데 실패했다. TTS 테이크마다
    쉼표 사이가 들쭉날쭉해서(강우규 130ms / 이회영 350ms / 안경신 440ms) 임계값에
    걸러지면 맨 앞 묵음까지 밀려나 문장 전체가 남는다.

    그래서 **묵음 구간을 전부 찾은 뒤 맨 끝(뒤쪽 여백)과 맨 앞(앞쪽 여백)을 빼고
    마지막 것**을 쓴다. 길이에 기대지 않으므로 테이크가 달라져도 안 깨진다.
    """
    sr, d = read(path)
    win = int(sr * 0.01)                      # 10ms
    env = [max(abs(x) for x in d[i:i + win]) or 0 for i in range(0, len(d) - win, win)]
    thr = max(env) * rel
    voiced = [e > thr for e in env]
    n = len(voiced)

    runs, i = [], 0                           # 묵음 구간 [시작, 끝) 단위: 프레임
    while i < n:
        if not voiced[i]:
            j = i
            while j < n and not voiced[j]:
                j += 1
            if (j - i) * 10 >= gap_ms:
                runs.append((i, j))
            i = j
        else:
            i += 1

    inner = [r for r in runs if r[0] > 0 and r[1] < n]   # 앞뒤 여백 제외
    if not inner:
        return 0.0
    return inner[-1][1] * win / sr


GAP_MS, REL = 50, 0.06     # 이 조합만 쓴다. 아래 주석 참고.


def inner_silences(path, gap_ms=GAP_MS, rel=REL):
    """앞뒤 여백을 뺀 묵음 구간 목록. 정상 테이크라면 쉼표 자리 하나만 나온다."""
    sr, d = read(path)
    win = int(sr * 0.01)
    env = [max(abs(x) for x in d[i:i + win]) or 0 for i in range(0, len(d) - win, win)]
    thr = max(env) * rel
    voiced = [e > thr for e in env]
    n = len(voiced)
    runs, i = [], 0
    while i < n:
        if not voiced[i]:
            j = i
            while j < n and not voiced[j]:
                j += 1
            if (j - i) * 10 >= gap_ms:
                runs.append((i * win / sr, j * win / sr))
            i = j
        else:
            i += 1
    return [r for r in runs if r[0] > 0 and r[1] * sr / win < n], len(d) / sr


def find_cut(path, syllables):
    """쉼표 자리를 찾는다. **임계값은 절대 풀지 않는다.**

    한때 '못 찾으면 임계값을 낮춰 재시도'하도록 짰다가 이름 한가운데(음절 사이
    약한 지점)를 쉼표로 착각해 이름이 잘려나갔다. 느슨하게 볼수록 이름 안에서
    끊길 위험만 커진다. 기준을 못 넘으면 **다시 합성하는 것이 맞다.**
    """
    runs, total = inner_silences(path)
    if not runs:
        return None, "묵음 구간을 못 찾음"
    # **첫 묵음이 쉼표 자리다.** 캐리어는 "그의 이름은, ○○○." 한 문장이라
    # 이름 앞의 사이는 쉼표 하나뿐이고, 그 뒤에 더 있다면 이름 안쪽이다
    # ("가네코 후미코"처럼 띄어쓰기가 있는 이름은 묵음이 3개까지 나온다).
    # 한때 마지막 묵음을 썼다가 이름 한가운데가 잘렸다.
    cut = runs[0][1]
    seg = total - cut
    lo, hi = 0.20 * syllables, 0.55 * syllables   # 실측 0.24~0.38초/음절
    if not (lo <= seg <= hi):
        return None, f"이름 길이 {seg:.2f}s가 기대범위({lo:.2f}~{hi:.2f}s) 밖"
    return cut, f"{seg:.2f}s / {syllables}음절"


def main(name, out_path):
    key = api_key()
    vid = voice_id(key, VOICE_NAME)
    tmp = out_path + ".carrier.wav"
    syl = len([c for c in name if "가" <= c <= "힣"])
    for attempt in range(1, 6):
        synth(key, vid, CARRIER.format(name=name), tmp)   # 본문과 같은 tonedown
        cut, how = find_cut(tmp, syl)
        if cut is not None:
            break
        print(f"  [{attempt}/5] {how} — 다시 합성한다")
    if cut is None:
        raise RuntimeError(f"'{name}' 캐리어에서 이름 경계를 찾지 못했다. 수동 확인 필요")
    print(f"  캐리어 '{CARRIER.format(name=name)}' — 이름 시작 {cut:.2f}s ({how})")
    subprocess.run(["ffmpeg", "-y", "-ss", f"{cut:.3f}", "-i", tmp,
                    "-af", f"atempo={BODY_TEMPO}", "-ar", "44100", "-ac", "1", out_path],
                   check=True, capture_output=True)
    return out_path


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
