#!/usr/bin/env bash
# TOP-150: run the prediction stack on a point-in-time top-150 dollar-volume
# universe (stocks only — funds excluded at ranking).
#
#   scripts/launch_top150.sh market    # membership@150 + workset -> results/Top150/m1x150
#   scripts/launch_top150.sh stage1    # LGBM walk-forward + gates
#   scripts/launch_top150.sh stage2    # GRU+CNN+FinBERT (GPU)
#   scripts/launch_top150.sh stage3    # meta gate + barrier book + CPCV
#   scripts/launch_top150.sh predict   # latest-date scores -> target book
#   scripts/launch_top150.sh exp       # variant sweep -> results/Top150/derived/top150/exp
#
# VOLUME CONTRACT (non-negotiable) — one volume, crimtr8kbf, mounted at /workspace:
#   data/, m1/, m1x/, ... (the root)  owned by a SEPARATE download system. READ-ONLY:
#                 the pod pulls its inputs via S3 GETs into container-local /scratch
#                 and never opens them on the mount. This repo does not fetch,
#                 validate, build or repair anything there.
#   results/Top150/  everything this repo writes (m1x150, derived/top150/*, models,
#                 ledger, reports, code, _pod_logs) and nothing else.
#
# Enforcement is central, not here: scripts/_common.sh owns the prefix and the only
# S3 writer, launch_predict.sh asserts every pod write path is under it, and
# pod_bootstrap_predict.sh refuses to run a job whose write paths are not.
set -euo pipefail
JOB="${1:?usage: launch_top150.sh <market|test|stage1|stage2|stage3|predict|exp>}"

export SRC_VOLUME_ID="${SRC_VOLUME_ID:-crimtr8kbf}"
R=/workspace/results/Top150      # == VOL_RESULTS in scripts/_common.sh
export MARKET_DIR="${MARKET_DIR:-$R/m1x150}"
export UNIVERSE_SIZE="${UNIVERSE_SIZE:-150}"
export SYSTEM_CONFIG="${SYSTEM_CONFIG:-configs/system_top150.yaml}"
export OUT_DIR="${OUT_DIR:-$R/derived/top150/${JOB}}"
export SCORES_DIR="${SCORES_DIR:-$R/derived/top150/stage2}"
export SCORES_DIR_ALT="${SCORES_DIR_ALT:-$R/derived/top150/stage1}"

exec "$(dirname "$0")/launch_predict.sh" "$JOB"
