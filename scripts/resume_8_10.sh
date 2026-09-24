#!/bin/zsh
# 쿼터 해제(2026-09-14 19:59)를 기다렸다가 8~10화 이미지를 채우고 렌더한다.
# 중간에 쿼터가 또 걸리면 gen_images.py가 거기서 멈추므로, 그 시점까지 만든 것만 남는다.
set -u
cd "/Users/namkyeongmo/Desktop/Claude/yt_1/이름을 부르다" || exit 1

TARGET=1789383900          # 19:59 + 5분 여유
NOW=$(date +%s)
WAIT=$((TARGET - NOW))
if [ "$WAIT" -gt 0 ]; then
  echo "[$(date '+%H:%M:%S')] 쿼터 해제까지 ${WAIT}초 대기"
  sleep "$WAIT"
fi

echo "[$(date '+%H:%M:%S')] 이미지 생성 시작"
python3 scripts/gen_images.py kang8_ sch_   # 10화(seok_)는 인물 교체로 보류
echo "[$(date '+%H:%M:%S')] 이미지 단계 종료"

for pair in 08_kang:dok_08_kang 09_schofield:dok_09_schofield; do
  js="${pair%%:*}"; slug="${pair##*:}"
  # 그 회차 이미지가 다 있을 때만 렌더한다 — 빠진 컷이 있으면 build_episode가 죽는다
  missing=$(python3 - "$js" <<'PY'
import json, os, sys
d = json.load(open(f"drafts/script_dok_{sys.argv[1]}.json"))
print(sum(1 for s in d["segments"]
          if s["image"].startswith("output/images/") and not os.path.exists(s["image"])))
PY
)
  if [ "$missing" != "0" ]; then
    echo "[$(date '+%H:%M:%S')] $js — 이미지 ${missing}장 부족, 렌더 건너뜀"
    continue
  fi
  echo "[$(date '+%H:%M:%S')] $js 렌더 시작"
  python3 scripts/build_episode.py "drafts/script_dok_${js}.json" 2>&1 | tail -3
done

echo "[$(date '+%H:%M:%S')] 완료"
ls -la output/최종본/
