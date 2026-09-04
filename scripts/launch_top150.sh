#!/usr/bin/env bash
# TOP-150 EXPERIMENT (branch top200): run the prediction stack on a
# point-in-time top-150 dollar-volume universe (stocks only — funds excluded
# at ranking).
#
#   scripts/launch_top150.sh market    # membership@150 + workset -> /workspace/m1x150
#   scripts/launch_top150.sh stage1    # LGBM walk-forward + gates
#   scripts/launch_top150.sh stage2    # GRU+CNN+FinBERT (GPU)
#   scripts/launch_top150.sh stage3    # meta gate + barrier book + CPCV
#
# Volume contract (2026-09-01, non-negotiable):
#   crimtr8kbf  — data SOURCE only. NEVER mounted, NEVER written; the pod
#                 reads it via S3 GETs into container-local /scratch.
#   k4cli3aj48  — calc volume, mounted at /workspace. Holds ONLY computed
#                 artifacts (m1x150, derived/top150/*, models, ledger, logs);
#                 raw data is never copied onto it.
set -euo pipefail
JOB="${1:?usage: launch_top150.sh <market|test|stage1|stage2|stage3|predict>}"

export RUNPOD_VOLUME_ID_OVERRIDE="${CALC_VOLUME_ID:-k4cli3aj48}"
export SRC_VOLUME_ID="${SRC_VOLUME_ID:-crimtr8kbf}"
if [ "$RUNPOD_VOLUME_ID_OVERRIDE" = "$SRC_VOLUME_ID" ]; then
  echo "refusing: calc volume == source volume ($SRC_VOLUME_ID) — the source is read-only" >&2
  exit 2
fi
if [ "$RUNPOD_VOLUME_ID_OVERRIDE" = "crimtr8kbf" ] || [ "$RUNPOD_VOLUME_ID_OVERRIDE" = "8qik4zxpxq" ]; then
  echo "refusing: $RUNPOD_VOLUME_ID_OVERRIDE is a protected data volume — it must never be mounted by this experiment" >&2
  exit 2
fi

export MARKET_DIR="${MARKET_DIR:-/workspace/m1x150}"
export UNIVERSE_SIZE="${UNIVERSE_SIZE:-150}"
export SYSTEM_CONFIG="${SYSTEM_CONFIG:-configs/system_top150.yaml}"
export OUT_DIR="${OUT_DIR:-/workspace/derived/top150/${JOB}}"
export SCORES_DIR="${SCORES_DIR:-/workspace/derived/top150/stage2}"
export SCORES_DIR_ALT="${SCORES_DIR_ALT:-/workspace/derived/top150/stage1}"

exec "$(dirname "$0")/launch_predict.sh" "$JOB"
