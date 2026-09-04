#!/usr/bin/env bash
# Shared by the helpers in this directory. There is ONE definition of the volume
# contract in this repo — scripts/_common.sh — and this just adopts it, so the
# helpers and the launchers can never drift apart on which volume is writable.
#
#   BUCKET / CALC_BUCKET   k4cli3aj48 — calc volume; every output lives here
#   SRC_BUCKET             crimtr8kbf — data source, READ-ONLY (use src_s3)
#
# Sourced, not executed.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
. "$REPO/scripts/_common.sh"
CALC_BUCKET="$BUCKET"
: "${RUNPOD_API_KEY:?set in runpod/.env}"
