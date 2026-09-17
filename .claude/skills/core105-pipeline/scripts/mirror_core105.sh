#!/usr/bin/env bash
# Pull CORE-105 results from results/Core105 on the data volume (crimtr8kbf), enforce
# G-02 against the source tape (the same volume's data/, read-only), and rebuild
# reports/core105 — the bundle the backend
# serves on the core105/top200 branches (and serve_core105_console.sh on :8790).
#
#   mirror_core105.sh                # daily: suggestions + bundle rebuild
#   FULL_MIRROR=1 mirror_core105.sh  # after a stage1-3 rerun: also re-pull stage artifacts
#
# build_reports.py wants a FLAT src dir; stage outputs live in subdirs, so this
# stages everything flat in a temp dir (same shape the 2026-09-01 bundle used).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/_env105.sh"
cd "$REPO"
# Both directions go through the guarded accessors in scripts/_common.sh:
# res_s3 for results/Core105, src_s3 (read-only) for everything else on the volume.
say() { echo "[$(date -u +%H:%M:%SZ)] mirror150: $*"; }

# ---- pull the book (daily artifact) -----------------------------------------
mkdir -p derived/core105/predict
res_s3 cp derived/core105/predict/suggestions.json \
  ./derived/core105/predict/suggestions.json --quiet
res_s3 cp derived/core105/predict/suggestions.md \
  ./reports/suggestions_core105.md --quiet 2>/dev/null || true

# ---- FULL_MIRROR: stage artifacts (quarterly research refresh) ---------------
if [ "${FULL_MIRROR:-}" = "1" ]; then
  for st in stage1 stage2 stage3; do
    say "pulling $st from $RESULTS"
    res_s3 cp "derived/core105/$st/" "./derived/core105/$st/" --recursive --quiet
  done
fi

# ---- G-02: the book must price the newest SOURCE day-file ----------------------
AS_OF=$(python3 -c "import json;print(json.load(open('derived/core105/predict/suggestions.json')).get('as_of_close',''))")
NEWEST=$(src_s3 ls "$SRC_BUCKET/data/eod_bulk/US/" | awk '{print $4}' | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}\.json$' | sort | tail -1 | sed 's/\.json$//')
if [ -z "$AS_OF" ] || [ "$AS_OF" != "$NEWEST" ]; then
  say "G-02 FAIL: suggestions as_of_close='$AS_OF' != newest source day-file '$NEWEST'"
  say "the book priced a stale close — rerun launch_core105.sh market + predict; NOT publishing"
  exit 1
fi
say "G-02 OK: as_of_close=$AS_OF matches newest source day-file"

# ---- stage a flat src dir and rebuild the bundle -----------------------------
STAGE_SRC=$(mktemp -d "${TMPDIR:-/tmp}/core105_src.XXXXXX")
trap 'rm -rf "$STAGE_SRC"' EXIT
cp derived/core105/predict/suggestions.json "$STAGE_SRC/"
find derived/core105/stage1 derived/core105/stage2 derived/core105/stage3 \
  -maxdepth 1 \( -name '*.json' -o -name '*.parquet' \) -exec cp {} "$STAGE_SRC/" \; 2>/dev/null || true
# session grid comes from the SOURCE volume's m1 (read-only GET)
src_s3 cp "$SRC_BUCKET/m1/sessions.parquet" "$STAGE_SRC/sessions.parquet" --quiet

say "rebuilding reports/core105"
SYSTEM_CONFIG=configs/system_core105.yaml \
  python3 tools/build_reports.py --src "$STAGE_SRC" --out reports/core105
# ---- publish: MongoDB is what the deployed UI reads --------------------------
# reports/core105 stays the local record (and what serve_core105_console.sh
# serves); the deployed backend (Vercel) reads only what is published here.
if [ "${PUBLISH_MONGO:-1}" = "1" ]; then
  say "publishing reports/core105 to MongoDB"
  python3 tools/publish_mongo.py --src reports/core105 --bundle core105
else
  say "PUBLISH_MONGO=0 — bundle rebuilt locally, NOT published to MongoDB"
fi
say "DONE — deployed UI shows the published bundle; locally: scripts/serve_core105_console.sh (:8790)"
