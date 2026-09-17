#!/usr/bin/env bash
# CORE-105: run the prediction stack on the FIXED 105-name universe listed in
# configs/system_core105.yaml (universe.tickers). No dollar-volume ranking, no
# hysteresis, no fund exclusion — SPY and QQQ are deliberate members. The list is
# part of config_hash, so editing it forces a full refit.
#
#   scripts/launch_core105.sh market    # fixed membership + workset -> results/Core105/m1x105
#   scripts/launch_core105.sh stage1    # LGBM walk-forward + gates
#   scripts/launch_core105.sh stage2    # GRU+CNN+FinBERT (GPU)
#   scripts/launch_core105.sh stage3    # meta gate + barrier book + CPCV
#   scripts/launch_core105.sh predict   # latest-date scores -> target book
#   scripts/launch_core105.sh exp       # variant sweep -> results/Core105/derived/core105/exp
#
# VOLUME CONTRACT (non-negotiable) — one volume, crimtr8kbf, mounted at /workspace:
#   data/, m1/, m1x/, ... (the root)  owned by a SEPARATE download system. READ-ONLY:
#                 the pod pulls its inputs via S3 GETs into container-local /scratch
#                 and never opens them on the mount. This repo does not fetch,
#                 validate, build or repair anything there.
#   results/Core105/  everything this repo writes (m1x105, derived/core105/*, models,
#                 ledger, reports, code, _pod_logs) and nothing else.
#
# Enforcement is central, not here: scripts/_common.sh owns the prefix and the only
# S3 writer, launch_predict.sh asserts every pod write path is under it, and
# pod_bootstrap_predict.sh refuses to run a job whose write paths are not.
set -euo pipefail
JOB="${1:?usage: launch_core105.sh <market|test|stage1|stage2|stage3|predict|exp>}"

export SRC_VOLUME_ID="${SRC_VOLUME_ID:-crimtr8kbf}"
R=/workspace/results/Core105      # == VOL_RESULTS in scripts/_common.sh
export MARKET_DIR="${MARKET_DIR:-$R/m1x105}"
export UNIVERSE_SIZE="${UNIVERSE_SIZE:-105}"   # informational in fixed_list mode
export SYSTEM_CONFIG="${SYSTEM_CONFIG:-configs/system_core105.yaml}"
export OUT_DIR="${OUT_DIR:-$R/derived/core105/${JOB}}"
export SCORES_DIR="${SCORES_DIR:-$R/derived/core105/stage2}"
export SCORES_DIR_ALT="${SCORES_DIR_ALT:-$R/derived/core105/stage1}"

exec "$(dirname "$0")/launch_predict.sh" "$JOB"
