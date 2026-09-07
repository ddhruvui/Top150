#!/usr/bin/env bash
# Safety net: terminate any leftover "investopediaclaude-*" pods (predict-market,
# predict-stage1, …) that failed to self-terminate. Lists pods via the account API and
# DELETEs each match. Run this when a pod was launched but never died — notably the
# broken-host case in the top150-pipeline skill (rule 4): no bootstrap log within ~5 min
# means it will bill forever while RUNNING and never start — and the "terminate attempt
# N not confirmed" loop, where the pod's own DELETE never gets a 204.
#
# Uses curl for the DELETE (the laptop's python.org build has no CA bundle, so urllib
# fails with CERTIFICATE_VERIFY_FAILED — observed 2026-09-07). KILL_MATCH overrides the
# name prefix; KILL_IDS="id1 id2" deletes exactly those ids.
. "$(dirname "$0")/_common.sh"
: "${RUNPOD_API_KEY:?account rpa_ key, set in runpod/.env}"
MATCH="${KILL_MATCH:-investopediaclaude-}"

if [ -n "${KILL_IDS:-}" ]; then
  IDS="$KILL_IDS"
else
  IDS=$(curl -sS --max-time 30 https://rest.runpod.io/v1/pods -H "Authorization: Bearer $RUNPOD_API_KEY" \
    | MATCH="$MATCH" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
pods = d if isinstance(d, list) else d.get("pods", d.get("data", []))
print(" ".join(p["id"] for p in pods if str(p.get("name") or "").startswith(os.environ["MATCH"])))')
fi
[ -n "$IDS" ] || { echo "no pods matching '$MATCH'"; exit 0; }
killed=0
for pid in $IDS; do
  code=$(curl -sS --max-time 60 -o /dev/null -w '%{http_code}' -X DELETE \
    "https://rest.runpod.io/v1/pods/$pid" -H "Authorization: Bearer $RUNPOD_API_KEY")
  case "$code" in
    200|204) echo "deleted $pid -> $code"; killed=$((killed + 1)) ;;
    404)     echo "already gone $pid" ;;
    *)       echo "FAILED $pid: HTTP $code" >&2 ;;
  esac
done
echo "killed $killed pod(s)"
