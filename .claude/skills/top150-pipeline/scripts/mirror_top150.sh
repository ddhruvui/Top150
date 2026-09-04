#!/usr/bin/env bash
# Pull TOP-150 results off the calc volume (k4cli3aj48), enforce G-02 against the
# PROD tape (crimtr8kbf), and rebuild reports/top150 — the bundle the backend
# serves on the top150/top200 branches (and serve_top150_console.sh on :8790).
#
#   mirror_top150.sh                # daily: suggestions + bundle rebuild
#   FULL_MIRROR=1 mirror_top150.sh  # after a stage1-3 rerun: also re-pull stage artifacts
#
# build_reports.py wants a FLAT src dir; stage outputs live in subdirs, so this
# stages everything flat in a temp dir (same shape the 2026-09-01 bundle used).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/_env150.sh"
cd "$REPO"
S3=(aws s3 --region "$RUNPOD_S3_REGION" --endpoint-url "$RUNPOD_S3_ENDPOINT")
say() { echo "[$(date -u +%H:%M:%SZ)] mirror150: $*"; }

# ---- pull the book (daily artifact) -----------------------------------------
mkdir -p derived/top150/predict
"${S3[@]}" cp "$CALC_BUCKET/derived/top150/predict/suggestions.json" \
  derived/top150/predict/suggestions.json --quiet
"${S3[@]}" cp "$CALC_BUCKET/derived/top150/predict/suggestions.md" \
  reports/suggestions_top150.md --quiet 2>/dev/null || true

# ---- FULL_MIRROR: stage artifacts (quarterly research refresh) ---------------
if [ "${FULL_MIRROR:-}" = "1" ]; then
  for st in stage1 stage2 stage3; do
    say "pulling $st from calc volume"
    "${S3[@]}" cp "$CALC_BUCKET/derived/top150/$st/" "derived/top150/$st/" \
      --recursive --quiet
  done
fi

# ---- G-02: the book must price the newest PROD day-file ----------------------
AS_OF=$(python3 -c "import json;print(json.load(open('derived/top150/predict/suggestions.json')).get('as_of_close',''))")
NEWEST=$("${S3[@]}" ls "$SRC_BUCKET/data/eod_bulk/US/" | awk '{print $4}' | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}\.json$' | sort | tail -1 | sed 's/\.json$//')
if [ -z "$AS_OF" ] || [ "$AS_OF" != "$NEWEST" ]; then
  say "G-02 FAIL: suggestions as_of_close='$AS_OF' != newest prod day-file '$NEWEST'"
  say "the book priced a stale close — rerun launch_top150.sh market + predict; NOT publishing"
  exit 1
fi
say "G-02 OK: as_of_close=$AS_OF matches newest prod day-file"

# ---- stage a flat src dir and rebuild the bundle -----------------------------
STAGE_SRC=$(mktemp -d "${TMPDIR:-/tmp}/top150_src.XXXXXX")
trap 'rm -rf "$STAGE_SRC"' EXIT
cp derived/top150/predict/suggestions.json "$STAGE_SRC/"
find derived/top150/stage1 derived/top150/stage2 derived/top150/stage3 \
  -maxdepth 1 \( -name '*.json' -o -name '*.parquet' \) -exec cp {} "$STAGE_SRC/" \; 2>/dev/null || true
# session grid comes from the PROD volume's m1 (read-only GET)
"${S3[@]}" cp "$SRC_BUCKET/m1/sessions.parquet" "$STAGE_SRC/sessions.parquet" --quiet

say "rebuilding reports/top150"
SYSTEM_CONFIG=configs/system_top150.yaml \
  python3 tools/build_reports.py --src "$STAGE_SRC" --out reports/top150
say "DONE — serve with: scripts/serve_top150_console.sh (:8790), or the branch-aware backend on top150/top200"
