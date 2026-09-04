#!/usr/bin/env bash
# Shared: load runpod/.env, then export BOTH volume handles for the top-150 experiment.
#   CALC_BUCKET  s3://k4cli3aj48  — calc volume the pods mount; ALL outputs + _pod_logs live here
#   SRC_BUCKET   s3://crimtr8kbf  — prod data source, READ-ONLY (never write to it from here)
# Sourced, not executed.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
ENVF="$REPO/data_acquisition/runpod/.env"
[ -f "$ENVF" ] || { echo "missing $ENVF" >&2; exit 1; }
set -a; . "$ENVF"; set +a
: "${RUNPOD_VOLUME_ID:?set in runpod/.env}"
: "${RUNPOD_API_KEY:?set in runpod/.env}"
CALC_VOLUME_ID="${CALC_VOLUME_ID:-k4cli3aj48}"
CALC_BUCKET="s3://$CALC_VOLUME_ID"
SRC_BUCKET="s3://$RUNPOD_VOLUME_ID"
if [ "$CALC_VOLUME_ID" = "$RUNPOD_VOLUME_ID" ]; then
  echo "refusing: CALC_VOLUME_ID == prod volume ($RUNPOD_VOLUME_ID)" >&2; exit 2
fi
