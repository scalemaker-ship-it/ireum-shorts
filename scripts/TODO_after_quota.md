# 이미지 주간 한도가 풀린 뒤 할 일

**리셋: 2026-09-27 23:38** (codex 이미지 생성 주간 크레딧)

## 1. 17화 전용 배경 만들기 (유일한 미완 항목)

17화 03번(표적 배경 — "그 무렵 의열단원들이 잇따라 부산경찰서에 붙잡히고 있었다")에
**8화 강기동의 `kang8_03_cell`을 임시로 빌려 쓰고 있다.**

```
cd "이름을 부르다"
python3 scripts/gen_images.py park_12        # park_12_lockup 생성 (프롬프트는 SCENES에 있음)
```

그 다음 대본의 03번 이미지를 바꾸고 다시 렌더한다:

```
python3 - <<'PY'
import json
p='drafts/script_dok_17_park.json'
s=json.load(open(p,encoding='utf-8'))
next(x for x in s['segments'] if x['id']=='03_setup')['image']="output/images/park_12_lockup.png"
s['images_plan']['03_setup']="1920년대 경찰서 유치장: 나무 창살과 어두운 복도, 바닥에 떨어진 빛. 사람 없음"
json.dump(s, open(p,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
PY
find output/video -name "*.png" -delete
python3 scripts/build_episode.py drafts/script_dok_17_park.json
ffmpeg -i output/최종본/dok_17_park.mp4 -c:v libx264 -crf 30 -preset slow \
       -c:a aac -b:a 96k output/preview/dok_17_park.mp4 -y
python3 scripts/build_archive_page.py
```

**임시본으로도 영상은 완성돼 있으므로 급한 일은 아니다.** 교체하면 더 정확해질 뿐이다.

## 2. 8화 `portrait` 필드 누락 (선택)

`drafts/script_dok_08_kang.json`에 `portrait` 필드가 없다(`None`).
빈 인화지 회차라 `09_cta`의 이미지·크레딧은 정상이고 영상도 문제없이 나와 있다.
**일관성 차원의 정리이고 재렌더는 필요 없다.**

```json
"portrait": "assets/photos/blank_plate.png",
```

## ⚠️ 잊지 말 것

- `gen_images.py` 출력을 **`tail`로 자르지 말 것.** 자르면 한도 메시지와 리셋 시각이 사라진다.
- 대기 스크립트 `fill_and_build.sh`는 **날짜까지** 받는다: `"2026-09-27 23:40"`.
  HHMM만 주면 자정을 못 넘는다(실제로 한 번 당했다).
- 20화 06번 음성은 **`pitch_fall.py` 후처리본**이다. TTS를 다시 뽑으면 사라진다.
  원본·처리본 모두 `output/audio/locked_takes/ep20_ahn_06_reveal_*`에 있다.
