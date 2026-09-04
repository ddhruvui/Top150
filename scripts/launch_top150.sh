#!/usr/bin/env bash
# TOP-150: run the prediction stack on a point-in-time top-150 dollar-volume
# universe (stocks only — funds excluded at ranking).
#
#   scripts/launch_top150.sh market    # membership@150 + workset -> /workspace/m1x150
#   scripts/launch_top150.sh stage1    # LGBM walk-forward + gates
#   scripts/launch_top150.sh stage2    # GRU+CNN+FinBERT (GPU)
#   scripts/launch_top150.sh stage3    # meta gate + barrier book + CPCV
#   scripts/launch_top150.sh predict   # latest-date scores -> target book
#   scripts/launch_top150.sh exp       # variant sweep -> /workspace/derived/top150/exp
#
# VOLUME CONTRACT (non-negotiable):
#   crimtr8kbf  — data SOURCE only. NEVER mounted, NEVER written. The pod reads
#                 it via S3 GETs into container-local /scratch. A SEPARATE system
#                 owns every vendor download that fills it; this repo does not
#                 fetch, validate, build or repair anything on it.
#   k4cli3aj48  — calc volume, mounted at /workspace. Holds ONLY computed
#                 artifacts (m1x150, derived/top150/*, models, ledger, logs).
#
# Enforcement is central, not here: scripts/_common.sh rebinds the mountable
# volume to the calc volume and refuses any protected id, launch_predict.sh
# re-asserts it before building the pod payload, and pod_bootstrap_predict.sh
# refuses to run without read-only source wiring.
set -euo pipefail
JOB="${1:?usage: launch_top150.sh <market|test|stage1|stage2|stage3|predict|exp>}"

export CALC_VOLUME_ID="${CALC_VOLUME_ID:-k4cli3aj48}"
export SRC_VOLUME_ID="${SRC_VOLUME_ID:-crimtr8kbf}"

export MARKET_DIR="${MARKET_DIR:-/workspace/m1x150}"
export UNIVERSE_SIZE="${UNIVERSE_SIZE:-150}"
export SYSTEM_CONFIG="${SYSTEM_CONFIG:-configs/system_top150.yaml}"
export OUT_DIR="${OUT_DIR:-/workspace/derived/top150/${JOB}}"
export SCORES_DIR="${SCORES_DIR:-/workspace/derived/top150/stage2}"
export SCORES_DIR_ALT="${SCORES_DIR_ALT:-/workspace/derived/top150/stage1}"

exec "$(dirname "$0")/launch_predict.sh" "$JOB"
