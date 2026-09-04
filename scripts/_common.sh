#!/usr/bin/env bash
# Sourced by every launcher and helper in this repo. Loads runpod/.env and sets
# the TWO volume handles this repo is allowed to know about.
#
# VOLUME CONTRACT (non-negotiable). This repo COMPUTES; it does not ingest.
#
#   SRC_BUCKET   crimtr8kbf  — the data SOURCE. STRICTLY READ-ONLY: never mounted
#                              by a pod, never written, never deleted from. A
#                              SEPARATE system owns every vendor download that
#                              fills it. Pods read it via S3 GETs into
#                              container-local /scratch (pod_bootstrap_predict.sh).
#   BUCKET       k4cli3aj48  — the CALC volume, mounted at /workspace. Everything
#                              this repo computes lands here and nowhere else.
#
# Because pod payloads mount "$RUNPOD_VOLUME_ID", that variable is deliberately
# REBOUND here to the calc volume. runpod/.env still names the source volume in
# RUNPOD_VOLUME_ID (that is what the download system calls it); after this file
# is sourced, RUNPOD_VOLUME_ID means "the volume we may write", by construction.
# There is no code path left in this repo that can mount the source.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"             # repo root
ENV_FILE="$ROOT/runpod/.env"

[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE — copy runpod/.env.example and fill it in" >&2; exit 1; }
set -a; . "$ENV_FILE"; set +a

: "${AWS_ACCESS_KEY_ID:?set in runpod/.env}"
: "${AWS_SECRET_ACCESS_KEY:?set in runpod/.env}"
: "${RUNPOD_S3_REGION:?set in runpod/.env}"
: "${RUNPOD_S3_ENDPOINT:?set in runpod/.env}"

# Volumes that hold vendor data. Read-only, always — listed by id so a typo in an
# override cannot silently aim a write at one. 8qik4zxpxq is the frozen
# pre-adoption archive; crimtr8kbf is the live source tape.
PROTECTED_VOLUMES="${PROTECTED_VOLUMES:-crimtr8kbf 8qik4zxpxq}"

# The source is whatever runpod/.env calls RUNPOD_VOLUME_ID, overridable for a
# drill; the calc volume defaults to k4cli3aj48.
SRC_VOLUME_ID="${SRC_VOLUME_ID:-${RUNPOD_VOLUME_ID:?set in runpod/.env}}"
CALC_VOLUME_ID="${CALC_VOLUME_ID:-${RUNPOD_VOLUME_ID_OVERRIDE:-k4cli3aj48}}"

is_protected() {   # $1 = volume id
  local v
  for v in $PROTECTED_VOLUMES; do [ "$1" = "$v" ] && return 0; done
  return 1
}

if [ "$CALC_VOLUME_ID" = "$SRC_VOLUME_ID" ]; then
  echo "refusing: calc volume == source volume ($SRC_VOLUME_ID) — the source is read-only" >&2
  exit 2
fi
if is_protected "$CALC_VOLUME_ID"; then
  echo "refusing: $CALC_VOLUME_ID is a protected data volume — it is read-only and must never be written or mounted" >&2
  exit 2
fi

# Rebind: from here on, the mountable/writable volume IS the calc volume.
RUNPOD_VOLUME_ID="$CALC_VOLUME_ID"

S3FLAGS="--region $RUNPOD_S3_REGION --endpoint-url $RUNPOD_S3_ENDPOINT"
BUCKET="s3://$CALC_VOLUME_ID"        # writes land here
SRC_BUCKET="s3://$SRC_VOLUME_ID"     # READS ONLY — never a cp/sync/rm destination

# Read-only accessor for the source tape. Use this instead of a bare `aws s3`
# whenever the source is involved: it refuses any subcommand that could mutate,
# and refuses a destination inside the source bucket.
src_s3() {   # src_s3 ls data/eod_bulk/US/   |   src_s3 cp data/x.json /tmp/x.json
  local sub="${1:?usage: src_s3 <ls|cp|sync> ...}"; shift
  case "$sub" in
    ls|cp|sync) ;;
    *) echo "src_s3: '$sub' is not a read-only operation on $SRC_BUCKET" >&2; return 2 ;;
  esac
  local a args=()
  for a in "$@"; do
    case "$a" in
      "$SRC_BUCKET"/*|"$SRC_BUCKET") args+=("$a") ;;
      s3://*|/*|.*|-*)               args+=("$a") ;;
      *)                             args+=("$SRC_BUCKET/$a") ;;
    esac
  done
  # For cp/sync the LAST positional is the destination; a source-bucket path there
  # would be a write. (ls takes no destination, so it is exempt.)
  if [ "$sub" != "ls" ]; then
    case "${args[$((${#args[@]} - 1))]}" in
      "$SRC_BUCKET"/*|"$SRC_BUCKET")
        echo "refusing: $SRC_BUCKET is read-only and cannot be a destination" >&2; return 2 ;;
    esac
  fi
  aws s3 "$sub" $S3FLAGS "${args[@]}"
}

command -v aws >/dev/null || { echo "aws CLI not found — install awscli" >&2; exit 1; }
