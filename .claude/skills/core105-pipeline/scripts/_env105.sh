#!/usr/bin/env bash
# Shared by the helpers in this directory. There is ONE definition of the volume
# contract in this repo — scripts/_common.sh — and this just adopts it, so the
# helpers and the launchers can never drift apart on what is writable.
#
#   SRC_BUCKET  s3://crimtr8kbf                 the data volume root — READ-ONLY (src_s3)
#   RESULTS     s3://crimtr8kbf/results/Core105  every output lives here (res_s3)
#
# Sourced, not executed.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
. "$REPO/scripts/_common.sh"
: "${RUNPOD_API_KEY:?set in runpod/.env}"
