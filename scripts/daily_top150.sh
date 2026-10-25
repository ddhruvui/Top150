#!/usr/bin/env bash
# The TOP150 daily loop, unattended (run by .github/workflows/daily.yml):
#
#   verify_source.py  ->  launch_top150.sh market  ->  launch_top150.sh predict
#
# Each job: launch -> require its bootstrap log within BOOT_WAIT_S (else it is on a
# broken host: delete that pod and fail) -> wait for its `job=` line -> require job=0.
# A pod exiting is not success; only job=0 is. The predict pod publishes the book
# itself, so nothing is mirrored back here.
#
#   SOURCE_FLOOR  ISO time verify_source.py treats as "fresh" (default: today 00:00 UTC)
#   BOOT_WAIT_S   seconds to wait for a bootstrap log (default 600)
#   JOB_WAIT_S    seconds to wait for a job's exit line (default 10800)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SK="$ROOT/.claude/skills/top150-pipeline/scripts"
BOOT_WAIT_S="${BOOT_WAIT_S:-600}"
JOB_WAIT_S="${JOB_WAIT_S:-10800}"
SOURCE_FLOOR="${SOURCE_FLOOR:-$(date -u +%Y-%m-%dT00:00:00Z)}"
POLL_S=30

echo "== verify_source (floor $SOURCE_FLOOR)"
"$SK/verify_source.py" "$SOURCE_FLOOR"

log_key() {  # newest _pod_logs name for this pod, or empty
  "$SK/vol150" ls _pod_logs/ | awk '{print $4}' | grep -- "predict-$1-$2" | sort | tail -1 || true
}

kill_pod() { KILL_IDS="$1" "$ROOT/scripts/killpod.sh" || true; }

run_job() {
  local job="$1" out pod key t0 f exit_line
  echo "== launch $job"
  out=$("$ROOT/scripts/launch_top150.sh" "$job")
  echo "$out"
  pod=$(printf '%s\n' "$out" | sed -n "s/^launched predict-$job pod: \([A-Za-z0-9]*\).*/\1/p")
  [ -n "$pod" ] || { echo "could not read pod id for $job" >&2; exit 1; }

  t0=$SECONDS; key=""
  while [ -z "$key" ]; do
    if (( SECONDS - t0 > BOOT_WAIT_S )); then
      echo "no bootstrap log for $job pod $pod after ${BOOT_WAIT_S}s — broken host, deleting it" >&2
      kill_pod "$pod"; exit 1
    fi
    sleep "$POLL_S"; key=$(log_key "$job" "$pod")
  done
  echo "bootstrap log: $key"

  f="${TMPDIR:-/tmp}/daily_$job.log"; t0=$SECONDS; exit_line=""
  while [ -z "$exit_line" ]; do
    if (( SECONDS - t0 > JOB_WAIT_S )); then
      echo "$job pod $pod gave no job= line after ${JOB_WAIT_S}s — deleting it" >&2
      kill_pod "$pod"; exit 1
    fi
    sleep "$POLL_S"
    "$SK/vol150" cp "_pod_logs/$key" "$f" --quiet || continue
    exit_line=$(grep -E '^job=[0-9]+ ' "$f" | tail -1 || true)
  done
  tail -n 25 "$f"
  # The pod self-terminates after its job= line; make sure it actually left.
  sleep 60; "$SK/pods" | grep -q "$pod" && kill_pod "$pod"
  [[ "$exit_line" == job=0\ * ]] || { echo "$job failed: $exit_line" >&2; exit 1; }
  echo "$job ok: $exit_line"
}

run_job market
run_job predict
