"""'이름을 부르다' 전용 TTS 생성.

잡학쿠키(`../../scripts/generate_tts.py`)와 설정이 다르므로 따로 둔다.
- 1인 내레이션(Piljae), 남녀 2인 대화 아님
- `tonedown` 감정 프리셋 + speed 0.95 → 소재 무게에 맞는 진중한 톤

주의: speed는 최상위 필드다. `prompt` 안에 넣으면 422(VALIDATION_ERROR)가 난다.
"""
import contextlib
import json
import os
import sys
import urllib.request
import wave

API = "https://api.typecast.ai/v1/text-to-speech"
VOICES = "https://api.typecast.ai/v1/voices"
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

VOICE_NAME = "Piljae"
MODEL = "ssfm-v30"
EMOTION = "tonedown"
SPEED = 0.95


def api_key():
    """.env는 프로젝트 최상단에 있다 (두 채널이 같은 키를 쓴다)."""
    for path in (os.path.join(BASE, ".env"), os.path.join(BASE, "..", ".env")):
        if os.path.exists(path):
            for line in open(path):
                if line.startswith("TYPECAST_API_KEY="):
                    return line.strip().split("=", 1)[1]
    raise RuntimeError("TYPECAST_API_KEY를 찾지 못했습니다")


def voice_id(key, name):
    req = urllib.request.Request(VOICES, headers={"X-API-KEY": key})
    for v in json.loads(urllib.request.urlopen(req).read()):
        if v["voice_name"] == name:
            return v["voice_id"]
    raise RuntimeError(f"보이스를 찾지 못했습니다: {name}")


def synth(key, vid, text, out_path):
    body = json.dumps({
        "voice_id": vid, "text": text, "model": MODEL,
        "prompt": {"emotion_preset": EMOTION},
        "speed": SPEED,
        "output": {"audio_format": "wav"},
    }).encode()
    req = urllib.request.Request(API, data=body, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "X-API-KEY": key})
    with urllib.request.urlopen(req) as resp, open(out_path, "wb") as f:
        f.write(resp.read())
    with contextlib.closing(wave.open(out_path)) as w:
        return w.getnframes() / w.getframerate()


def main(script_path, out_dir, only=None):
    """only에 세그먼트 id를 주면 그것만 다시 만든다.

    TTS는 같은 입력에도 길이·억양이 매번 달라지므로(실측 1.1~1.7초 편차),
    대본을 일부만 고쳤을 때 전체를 다시 뽑으면 이미 확정한 세그먼트의
    호흡까지 바뀐다. 고친 문장만 골라 뽑을 수 있어야 한다.
    """
    key = api_key()
    vid = voice_id(key, VOICE_NAME)
    script = json.load(open(script_path, encoding="utf-8"))
    os.makedirs(out_dir, exist_ok=True)

    total = 0.0
    for seg in script["segments"]:
        if only and seg["id"] not in only:
            continue
        if seg.get("locked_audio"):     # 확정 테이크는 건드리지 않는다
            print(f"  {seg['id']:12s} skip (locked)")
            continue
        d = synth(key, vid, seg["text"], os.path.join(out_dir, f"{seg['id']}.wav"))
        total += d
        print(f"  {seg['id']:12s} {d:5.2f}s")
    print(f"\n합계 {total:.1f}s  (1.15배속 적용 시 {total / 1.15:.1f}s)")


if __name__ == "__main__":
    sp = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "drafts/script_dok_01_kang.json")
    od = sys.argv[2] if len(sys.argv) > 2 else os.path.join(BASE, "output/audio/dok_01")
    only = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None
    main(sp, od, only)
