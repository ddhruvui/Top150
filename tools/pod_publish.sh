#!/usr/bin/env bash
# Pod-side publish: turn a finished predict job into the bundle the deployed UI
# reads, without anything leaving the cloud. pod_bootstrap_predict.sh runs this
# at the end of the predict pod once the job has exited 0. The laptop path
# (mirror_top150.sh) remains for pulling the record into git.
#
#   1. G-02: the book's as_of_close must equal the newest data/eod_bulk/US/
#      day-file ON THE SOURCE. That is a read-only LIST of the source bucket —
#      the same call mirror_top150.sh makes — and nothing in this file ever
#      writes there (volume contract: launch_top150.sh).
#   2. build the bundle: tools/build_reports.py over a flat staging dir of the
#      predict output, whatever stage1/2/3 artifacts sit on the calc volume, and
#      the D-11 session grid from the source prefetch.
#   3. publish: tools/publish_mongo.py -> MongoDB, which Vercel + Render show.
#   The built bundle is left on the calc volume (BUNDLE_OUT), so the exact
#   published record can be pulled into git without rebuilding it.
#
# Inputs (env):
#   OUT_DIR        predict output dir holding suggestions.json          required
#   DERIVED_ROOT   parent of stage1/ stage2/ stage3/                     default: dirname OUT_DIR
#   SESSIONS_PATH  D-11 session grid parquet                             default: /scratch/m1/sessions.parquet
#   BUNDLE         bundle name                                           default: top150
#   BUNDLE_OUT     where the built bundle is written                     default: /workspace/reports/$BUNDLE
#   SRC_VOLUME_ID, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
#   RUNPOD_S3_ENDPOINT, RUNPOD_S3_REGION                                 G-02 listing
#   MONGO_URI, DB_PASSWORD, MONGO_DB                                     publish
#   SYSTEM_CONFIG                                                        config hash for the bundle
# Exit: 0 published · 2 misconfigured · 3 G-02 failed (nothing published)
#       4 bundle build failed · 5 publish failed (bundle intact at BUNDLE_OUT)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
PY="${PYTHON:-$(command -v python3 || command -v python)}"
say() { echo "[$(date -u +%H:%M:%SZ)] publish: $*"; }

: "${OUT_DIR:?OUT_DIR (predict output dir) is required}"
BUNDLE="${BUNDLE:-top150}"
DERIVED_ROOT="${DERIVED_ROOT:-$(dirname "$OUT_DIR")}"
SESSIONS_PATH="${SESSIONS_PATH:-/scratch/m1/sessions.parquet}"
BUNDLE_OUT="${BUNDLE_OUT:-/workspace/reports/$BUNDLE}"
for v in SRC_VOLUME_ID AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY RUNPOD_S3_ENDPOINT MONGO_URI; do
  [ -n "${!v:-}" ] || { say "FATAL: $v unset — cannot publish"; exit 2; }
done
SUG="$OUT_DIR/suggestions.json"
[ -f "$SUG" ] || { say "FATAL: no $SUG — nothing to publish"; exit 2; }

# ---- 1. G-02 — read-only LIST of the source; never a write --------------------
AS_OF=$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1])).get('as_of_close',''))" "$SUG")
NEWEST=$(aws s3 ls --endpoint-url "$RUNPOD_S3_ENDPOINT" --region "${RUNPOD_S3_REGION:-eu-ro-1}" \
           "s3://${SRC_VOLUME_ID}/data/eod_bulk/US/" 2>/dev/null \
         | awk '{print $4}' | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}\.json$' | sort | tail -1 \
         | sed 's/\.json$//')
if [ -z "$NEWEST" ]; then
  say "FATAL: could not list the source day-files — G-02 cannot be evaluated; NOT publishing"
  exit 3
fi
if [ -z "$AS_OF" ] || [ "$AS_OF" != "$NEWEST" ]; then
  say "G-02 FAIL: as_of_close='$AS_OF' != newest source day-file '$NEWEST'"
  say "the book priced a stale close — rerun market + predict; NOT publishing"
  exit 3
fi
say "G-02 OK: as_of_close=$AS_OF matches the newest source day-file"

# ---- 2. build the bundle (flat staging dir, as build_reports.py expects) -------
STAGE=$(mktemp -d "${TMPDIR:-/tmp}/publish_src.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT
cp "$SUG" "$STAGE/"
n_art=0
for st in stage1 stage2 stage3; do
  [ -d "$DERIVED_ROOT/$st" ] || continue
  for f in "$DERIVED_ROOT/$st"/*.json "$DERIVED_ROOT/$st"/*.parquet; do
    [ -f "$f" ] && { cp "$f" "$STAGE/"; n_art=$((n_art + 1)); }
  done
done
if [ -f "$SESSIONS_PATH" ]; then
  cp "$SESSIONS_PATH" "$STAGE/sessions.parquet"
else
  say "!! no session grid at $SESSIONS_PATH — the Today page cannot date the next open"
fi
say "staged suggestions + $n_art stage artifacts from $DERIVED_ROOT -> building $BUNDLE_OUT"
mkdir -p "$BUNDLE_OUT"
"$PY" "$REPO/tools/build_reports.py" --src "$STAGE" --out "$BUNDLE_OUT" \
  || { say "FATAL: build_reports.py failed"; exit 4; }

# ---- 3. publish ----------------------------------------------------------------
"$PY" "$REPO/tools/publish_mongo.py" --src "$BUNDLE_OUT" --bundle "$BUNDLE" --seed-paper '' \
  || { say "FATAL: publish_mongo.py failed — bundle intact at $BUNDLE_OUT; mirror_top150.sh can publish it"; exit 5; }
say "PUBLISHED bundle '$BUNDLE' as of $AS_OF — the deployed UI shows it within ~30 s"
