#!/usr/bin/env bash
# Show what this repo keeps on the data volume (results/Core105): per-object listing + totals.
. "$(dirname "$0")/_common.sh"

if [ -n "${RUNPOD_API_KEY:-}" ]; then
  curl -sS "https://rest.runpod.io/v1/networkvolumes/$RUNPOD_VOLUME_ID" \
    -H "Authorization: Bearer $RUNPOD_API_KEY" 2>/dev/null \
    | python3 -c "import json,sys;d=json.load(sys.stdin);print(f\"Volume {d.get('id')} ({d.get('name')}): {d.get('size')} GB allocated in {d.get('dataCenterId')}\")" 2>/dev/null || true
fi

# Only this repo's prefix: the rest of the volume is the download system's, and a
# recursive listing of it runs to hundreds of thousands of objects.
echo "Contents of $RESULTS:"
res_s3 ls --recursive --summarize --human-readable
