#!/bin/zsh
# 이미지 쿼터가 풀리면 남은 배경을 채우고, 이미지가 다 찬 회차를 순서대로 렌더한다.
#
# ⚠️ codex 이미지 생성은 한도가 있다(한 창에 10장 안팎). 한도에 걸리면 gen_images.py가
#    거기서 멈추므로, 이 스크립트도 "채울 수 있는 만큼 채우고 렌더 가능한 것만 만드는" 구조다.
#    다음 창에서 다시 돌리면 이미 있는 파일은 건너뛰고 이어서 채운다.
#
# 사용: fill_and_build.sh ["YYYY-MM-DD HH:MM" 대기시각]
#       예) fill_and_build.sh "2026-09-22 01:27"
#
# ⚠️ 대기 시각은 **날짜까지** 준다. HHMM만 비교하면 자정을 못 넘는다 —
#    실제로 21:07에 "0127"을 기다리게 했더니 2107 > 127이라 루프가 즉시 끝나고
#    한도에 그대로 부딪혔다. 아래는 epoch 초로 비교한다.
set -u
cd "$(dirname "$0")/.."

WAIT_UNTIL="${1:-}"
if [[ -n "$WAIT_UNTIL" ]]; then
  TARGET=$(date -j -f "%Y-%m-%d %H:%M" "$WAIT_UNTIL" +%s) || {
    echo "대기 시각 형식이 잘못됐다: $WAIT_UNTIL (예: \"2026-09-22 01:27\")"; exit 1; }
  echo "== $WAIT_UNTIL 까지 대기 (현재 $(date '+%m-%d %H:%M'), $(( (TARGET - $(date +%s)) / 60 ))분 남음)"
  while [[ "$(date +%s)" -lt "$TARGET" ]]; do sleep 60; done
  echo "== 대기 종료 $(date '+%m-%d %H:%M')"
fi

echo "== 이미지 생성 (출력을 자르지 않는다 — 한도 메시지에 리셋 시각이 찍힌다)"
python3 scripts/gen_images.py shin seok park maria hul ahn20 2>&1

echo
echo "== 렌더 가능한 회차 확인"
READY=$(python3 - <<'PY'
import json, glob, os
out=[]
for p in sorted(glob.glob('drafts/script_dok_1[5-9]*.json'))+sorted(glob.glob('drafts/script_dok_20*.json')):
    s=json.load(open(p,encoding='utf-8'))
    if os.path.exists(s['output']): continue          # 이미 만든 편은 건너뛴다
    imgs=[x['image'] for x in s['segments'] if x['image'].startswith('output/images')]
    if all(os.path.exists(i) for i in imgs):
        out.append(os.path.basename(p)[len('script_dok_'):-len('.json')])
print(' '.join(out))
PY
)
echo "   → ${READY:-없음}"

for ep in ${=READY}; do
  echo
  echo "== 렌더 $ep"
  find output/video -name "*.png" -delete 2>/dev/null
  python3 scripts/build_episode.py "drafts/script_dok_${ep}.json" 2>&1 | tail -3
  ffmpeg -v error -i "output/최종본/dok_${ep}.mp4" \
    -c:v libx264 -crf 30 -preset slow -c:a aac -b:a 96k \
    "output/preview/dok_${ep}.mp4" -y
done
find output/video -name "*.png" -delete 2>/dev/null

echo
echo "== 남은 이미지"
python3 - <<'PY'
import json, glob, os
for p in sorted(glob.glob('drafts/script_dok_1[5-9]*.json'))+sorted(glob.glob('drafts/script_dok_20*.json')):
    s=json.load(open(p,encoding='utf-8'))
    imgs=[x['image'] for x in s['segments'] if x['image'].startswith('output/images')]
    left=[i for i in imgs if not os.path.exists(i)]
    done='완성' if os.path.exists(s['output']) else f'이미지 {len(left)}장 남음'
    print(f"  {s['episode']}화  {done}")
PY
