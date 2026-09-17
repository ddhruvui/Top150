#!/usr/bin/env bash
# Sourced by every launcher and helper in this repo. Loads runpod/.env and sets
# the volume handles this repo is allowed to know about.
#
# VOLUME CONTRACT (non-negotiable). This repo COMPUTES; it does not ingest.
#
# ONE volume since 2026-09-17: crimtr8kbf. The old calc volume k4cli3aj48 is
# retired; everything it held now lives under results/Core105/ on crimtr8kbf, with
# the same relative layout (k4cli3aj48:/X == crimtr8kbf:/results/Core105/X).
#
#   SRC_BUCKET  s3://crimtr8kbf                 the volume root. data/, m1/, m1x/ and
#                                               every other root tree belong to the
#                                               SEPARATE download system and are
#                                               STRICTLY READ-ONLY here: only ever
#                                               read, through src_s3.
#   RESULTS     s3://crimtr8kbf/results/Core105  the ONLY place this repo writes,
#                                               through res_s3. Other projects keep
#                                               their own results/<name>/ and are
#                                               never touched.
#
# Pods mount crimtr8kbf at /workspace and write only under VOL_RESULTS
# (/workspace/results/Core105); pod_bootstrap_predict.sh refuses any write path
# outside it. Their inputs still arrive as read-only S3 GETs into container-local
# /scratch, so the job processes never open a file under /workspace/data or m1.
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

# The calc-volume knobs are gone. A shell that still exports them is running the
# pre-2026-09-17 procedure: stop it rather than guess what it meant.
for _v in CALC_VOLUME_ID RUNPOD_VOLUME_ID_OVERRIDE; do
  if [ -n "${!_v:-}" ]; then
    echo "refusing: $_v is retired — k4cli3aj48 is gone and outputs live under results/Core105 on the data volume; unset it" >&2
    exit 2
  fi
done
unset _v

# Never mounted, never written: the frozen pre-adoption archive and the retired
# calc volume. Listed by id so a typo in an override cannot aim a pod at one.
RETIRED_VOLUMES="8qik4zxpxq k4cli3aj48"

# The data volume is whatever runpod/.env calls RUNPOD_VOLUME_ID (crimtr8kbf).
SRC_VOLUME_ID="${SRC_VOLUME_ID:-${RUNPOD_VOLUME_ID:?set in runpod/.env}}"
for _v in $RETIRED_VOLUMES; do
  if [ "$SRC_VOLUME_ID" = "$_v" ]; then
    echo "refusing: $SRC_VOLUME_ID is a retired volume — it must never be mounted or written" >&2
    exit 2
  fi
done
unset _v
# The volume pods mount. Deliberately not overridable separately: there is one.
RUNPOD_VOLUME_ID="$SRC_VOLUME_ID"

# Fixed, not an env knob: a different prefix could only ever be another project's.
RESULTS_PREFIX="results/Core105"

S3FLAGS="--region $RUNPOD_S3_REGION --endpoint-url $RUNPOD_S3_ENDPOINT"
SRC_BUCKET="s3://$SRC_VOLUME_ID"             # READS ONLY — never a write/rm target
RESULTS="$SRC_BUCKET/$RESULTS_PREFIX"        # the only write target
VOL_RESULTS="/workspace/$RESULTS_PREFIX"     # the same place as a pod sees it

# Both accessors take positionals FIRST, flags after:
#   src_s3 ls <path> [flags]            res_s3 ls [<path>] [flags]
#   src_s3 cp|sync <src> <dst> [flags]  res_s3 cp|sync|mv <src> <dst> [flags]
#                                       res_s3 rm <path> [flags]
# so the destination is always the second argument and cannot hide behind a
# trailing flag (the old src_s3 took the LAST argument as the destination, so
# `cp /tmp/x data/x --quiet` checked "--quiet" and wrote the source).

# Read-only accessor for the volume root. Bare relative paths are volume paths.
src_s3() {   # src_s3 ls data/eod_bulk/US/   |   src_s3 cp m1/sessions.parquet /tmp/s.parquet --quiet
  local sub="${1:?usage: src_s3 <ls|cp|sync> ...}"; shift
  case "$sub" in
    ls|cp|sync) ;;
    *) echo "src_s3: '$sub' is not a read-only operation on $SRC_BUCKET" >&2; return 2 ;;
  esac
  local src="${1:-}"
  case "$src" in
    "") [ "$sub" = "ls" ] || { echo "src_s3 $sub: missing source" >&2; return 2; }; src="$SRC_BUCKET/" ;;
    "$SRC_BUCKET"/*|"$SRC_BUCKET") ;;
    s3://*) echo "src_s3: $src is not on $SRC_BUCKET" >&2; return 2 ;;
    -*) echo "src_s3: put the path before flags ($src)" >&2; return 2 ;;
    *) src="$SRC_BUCKET/$src" ;;
  esac
  [ $# -gt 0 ] && shift
  if [ "$sub" = "ls" ]; then
    aws s3 ls $S3FLAGS "$src" "$@"; return
  fi
  local dst="${1:-}"
  # A read lands on local disk and nowhere else: any s3:// destination, or a bare
  # name that would resolve into the bucket, is refused.
  case "$dst" in
    ""|-*) echo "src_s3 $sub: missing destination (positionals before flags)" >&2; return 2 ;;
    s3://*) echo "refusing: src_s3 is read-only — destination $dst is not local disk" >&2; return 2 ;;
    /*|./*|../*) ;;
    *) echo "src_s3 $sub: destination must be an explicit local path (/abs or ./rel), got '$dst'" >&2; return 2 ;;
  esac
  shift
  local a
  for a in "$@"; do
    case "$a" in s3://*) echo "refusing: extra s3 path after the destination: $a" >&2; return 2 ;; esac
  done
  aws s3 "$sub" $S3FLAGS "$src" "$dst" "$@"
}

# _res_path <arg> — bare relative -> under RESULTS; s3:// on the data volume must
# already be under RESULTS; prints the resolved argument or fails.
_res_path() {
  local p="$1"
  case "$p" in
    -*) echo "res_s3: put paths before flags ($p)" >&2; return 2 ;;
    s3://*|/*|./*|../*) ;;
    *) p="$RESULTS/$p" ;;
  esac
  case "$p" in
    s3://*)
      # A key like results/Core105/../../data/x must not count as "under RESULTS".
      case "/${p#s3://}/" in *"/../"*|*"/./"*)
        echo "refusing: '.' or '..' segment in $p" >&2; return 2 ;; esac
      case "$p" in
        "$RESULTS"/*|"$RESULTS") ;;
        "$SRC_BUCKET"/*|"$SRC_BUCKET")
          echo "refusing: $p is outside $RESULTS — the rest of $SRC_BUCKET is read-only (use src_s3)" >&2; return 2 ;;
      esac ;;
  esac
  printf '%s\n' "$p"
}

# The only writer. Everything it can create, overwrite or delete is under RESULTS.
res_s3() {   # res_s3 ls _pod_logs/   |   res_s3 cp ./bundle.tgz code/predict/bundle.tgz
  local sub="${1:?usage: res_s3 <ls|cp|sync|mv|rm> ...}"; shift
  local n
  case "$sub" in
    ls|rm) n=1 ;;
    cp|sync|mv) n=2 ;;
    *) echo "res_s3: unsupported subcommand '$sub'" >&2; return 2 ;;
  esac
  if [ "$sub" = "ls" ] && { [ $# -eq 0 ] || [ "${1#-}" != "$1" ]; }; then
    aws s3 ls $S3FLAGS "$RESULTS/" "$@"; return
  fi
  [ $# -ge "$n" ] || { echo "res_s3 $sub: expected $n path(s) before flags" >&2; return 2; }
  local src dst=""
  src=$(_res_path "$1") || return 2
  [ "$n" = 2 ] && { dst=$(_res_path "$2") || return 2; }
  shift "$n"
  local a
  for a in "$@"; do
    case "$a" in s3://*) echo "refusing: extra s3 path after the positionals: $a" >&2; return 2 ;; esac
  done
  case "$sub" in
    ls) aws s3 ls $S3FLAGS "$src" "$@"; return ;;
    rm)
      case "$src" in "$RESULTS"/?*) ;; *)
        echo "refusing: rm target must be a path under $RESULTS/, got $src" >&2; return 2 ;; esac ;;
    cp|sync|mv)
      # Destination: local disk or RESULTS. A source on another bucket (the
      # retired calc volume during migration) is a read and is allowed for
      # cp/sync; mv would delete it, so mv's source must be local or RESULTS.
      case "$dst" in s3://*) case "$dst" in "$RESULTS"/*|"$RESULTS") ;; *)
        echo "refusing: destination $dst is outside $RESULTS" >&2; return 2 ;; esac ;; esac
      if [ "$sub" = "mv" ]; then
        case "$src" in s3://*) case "$src" in "$RESULTS"/?*) ;; *)
          echo "refusing: mv would delete $src, which is outside $RESULTS" >&2; return 2 ;; esac ;; esac
      fi ;;
  esac
  if [ "$n" = 2 ]; then aws s3 "$sub" $S3FLAGS "$src" "$dst" "$@"
  else aws s3 "$sub" $S3FLAGS "$src" "$@"; fi
}

command -v aws >/dev/null || { echo "aws CLI not found — install awscli" >&2; exit 1; }
