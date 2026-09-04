#!/usr/bin/env bash
# Launch the prediction stack on RunPod against the data volume.
#   scripts/launch_predict.sh test      # run the T-01..T-15 suite on a CPU pod
#   scripts/launch_predict.sh market    # build whole-market panel + universe (m1x) — CPU
#   scripts/launch_predict.sh stage1    # Stage-1 pipeline (features->LGBM->backtest->gates) — CPU
#   scripts/launch_predict.sh stage2    # Stage-2 GRU+CNN+FinBERT — GPU
#   scripts/launch_predict.sh predict   # latest-date scores -> target book -> suggestions — CPU
#
# USE_MARKET=1 (default) points stage1/predict at the m1x whole-market universe;
# KEEP_POD=1 leaves the pod alive for inspection.
#
# VOLUME CONTRACT: the pod mounts the CALC volume only. The data source is read
# STRICTLY via S3 GETs into container-local /scratch (the prefetch block in
# pod_bootstrap_predict.sh) — it is never mounted and never written. _common.sh
# rebinds RUNPOD_VOLUME_ID to the calc volume and refuses a protected id, so the
# payload built below cannot name the source volume; the assertion after it is a
# second lock on the one line that actually mounts something.
. "$(dirname "$0")/_common.sh"
REPO_ROOT="$ROOT"

# MongoDB settings for the pod-side publish (predict) come from the repo-root
# .env — the same file the laptop-side publisher and the backend read. Parsed
# line by line, never sourced: a URI holding Atlas's literal <db_password>
# would otherwise be read by the shell as two redirections. Shell values win.
load_env_file() {
  local line k v
  [ -f "$1" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line#"${line%%[![:space:]]*}"}"
    case "$line" in ''|'#'*) continue ;; esac
    case "$line" in *=*) ;; *) continue ;; esac
    k="${line%%=*}"; v="${line#*=}"
    k="${k#export }"; k="${k%"${k##*[![:space:]]}"}"
    v="${v#"${v%%[![:space:]]*}"}"; v="${v%"${v##*[![:space:]]}"}"
    case "$v" in
      \"*\") v="${v#\"}"; v="${v%\"}" ;;
      \'*\') v="${v#\'}"; v="${v%\'}" ;;
    esac
    [ -n "${!k:-}" ] || export "$k=$v"
  done < "$1"
}
load_env_file "$ROOT/.env"
# JSON string literal (quotes included) — for values that may carry odd characters.
jstr() { python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$1"; }

JOB="${1:-stage1}"
case "$JOB" in test|market|stage1|stage2|stage3|predict|exp) ;; *)
  echo "unknown job '$JOB' (test|market|stage1|stage2|stage3|predict|exp)" >&2; exit 2 ;; esac
: "${RUNPOD_API_KEY:?set in runpod/.env}"

DC="${RUNPOD_DATACENTER:-EU-RO-1}"
CPU_IMAGE="${RUNPOD_IMAGE:-python:3.11-slim}"
GPU_IMAGE="${RUNPOD_GPU_IMAGE:-runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04}"
FLAVORS="${RUNPOD_CPU_FLAVORS:-[\"cpu3c\",\"cpu3g\",\"cpu3m\",\"cpu5c\",\"cpu5g\",\"cpu5m\"]}"
GPU_TYPES="${RUNPOD_GPU_TYPES:-[\"NVIDIA GeForce RTX 4090\",\"NVIDIA RTX A5000\",\"NVIDIA A40\"]}"
VCPU="${RUNPOD_VCPU:-8}"        # stage1/market hold multi-GB panels: 8 vCPU -> 16 GB
# Container disk is host-local scratch; all data lives on the network volume, so this only
# holds the image + pip deps (~2 GB). It is a real placement constraint: EU-RO-1 refused
# 20 GB at every vCPU count on 2026-08-27 while 10 GB placed instantly. (The GPU path keeps
# 40 GB — the PyTorch image alone is ~20 GB.)
CPU_DISK="${RUNPOD_CONTAINER_DISK_GB:-10}"
# GPU FALLBACK for the CPU jobs (test/market/stage1/stage3/predict). EU-RO-1 CPU capacity
# disappears for hours and the volume pins us to that datacenter, so a CPU-only launcher can
# miss the open. GPU hosts are a separate pool, usually free when CPU is not, and carry far
# more RAM (A4500: 12 vCPU / 62 GB for ~$0.25/hr vs 8 vCPU / 16 GB on CPU). These jobs are
# pandas/LightGBM and never touch CUDA — the GPU is bought purely for the host slot, and it
# runs the CPU image + CPU pip set, not the PyTorch image. GPU_FALLBACK=0 disables.
GPU_FALLBACK="${GPU_FALLBACK:-1}"
GPU_FALLBACK_TYPES="${RUNPOD_GPU_FALLBACK_TYPES:-NVIDIA RTX A4500|NVIDIA RTX 4000 Ada Generation|NVIDIA GeForce RTX 3090|NVIDIA RTX A6000|NVIDIA GeForce RTX 4090|NVIDIA A40}"
# pymongo+dnspython+certifi: the pod-side publish (tools/pod_publish.sh) after predict
PIP_CPU="pandas pyarrow numpy PyYAML scipy lightgbm scikit-learn optuna pytest pymongo dnspython certifi"
PIP_GPU="pandas pyarrow numpy PyYAML scipy lightgbm scikit-learn optuna pytest transformers==4.44.2 sentencepiece"

RUNNING=$(curl -sS --max-time 30 https://rest.runpod.io/v1/pods \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" 2>/dev/null) || RUNNING=""
if printf '%s' "$RUNNING" | grep -q "investopediaclaude-predict-${JOB}"; then
  echo "SKIP: pod investopediaclaude-predict-${JOB} already running"; exit 0
fi

echo "Bundling prediction stack ..."
TMP_TGZ="$(mktemp -t predict-bundle).tgz"
( cd "$REPO_ROOT" && tar czf "$TMP_TGZ" \
    --exclude='__pycache__' --exclude='.pytest_cache' \
    src configs tests tools requirements.txt )

ENV_COMMON=$(cat <<JSON
    "JOB": "${JOB}",
    "USE_MARKET": "${USE_MARKET:-1}",
    "KEEP_POD": "${KEEP_POD:-}",
    "RUNPOD_TERMINATE_KEY": "${RUNPOD_API_KEY}",
    "OUT_DIR": "${OUT_DIR:-/workspace/derived/${JOB}}",
    "SCORES_DIR": "${SCORES_DIR:-/workspace/derived/stage2}",
    "NO_CPCV": "${NO_CPCV:-}",
    "LEDGER_PATH": "${LEDGER_PATH:-/workspace/ledger/trials.parquet}",
    "MODEL_DIR": "${MODEL_DIR:-/workspace/models}",
    "REFIT": "${REFIT:-auto}",
    "SCORES_DIR_ALT": "${SCORES_DIR_ALT:-/workspace/derived/stage1}",
    "VARIANTS_B64": "${VARIANTS_B64:-}",
    "SYSTEM_CONFIG": "${SYSTEM_CONFIG:-}"
JSON
)
# The pod ALWAYS mounts the calc volume and ALWAYS pulls its inputs from the
# source volume via read-only S3 GETs into /scratch. This used to be conditional
# ("experiment wiring"); it is now the only mode, because the unconditional path
# was the one that mounted the source tape and wrote to it.
ENV_COMMON="${ENV_COMMON},
    \"SRC_VOLUME_ID\": \"${SRC_VOLUME_ID}\",
    \"AWS_ACCESS_KEY_ID\": \"${AWS_ACCESS_KEY_ID}\",
    \"AWS_SECRET_ACCESS_KEY\": \"${AWS_SECRET_ACCESS_KEY}\",
    \"RUNPOD_S3_ENDPOINT\": \"${RUNPOD_S3_ENDPOINT}\",
    \"RUNPOD_S3_REGION\": \"${RUNPOD_S3_REGION}\",
    \"MARKET_DIR\": \"${MARKET_DIR:-/workspace/m1x150}\",
    \"UNIVERSE_SIZE\": \"${UNIVERSE_SIZE:-150}\""
# Pod-side publish: the predict pod gets the MongoDB credentials (from .env at
# the repo root) and publishes the bundle itself; nothing comes down to a
# laptop. PUBLISH_MONGO=0 launches without them (the laptop mirror still works).
if [ "$JOB" = "predict" ] && [ "${PUBLISH_MONGO:-1}" = "1" ]; then
  : "${MONGO_URI:?set MONGO_URI in .env at the repo root for the pod-side publish, or PUBLISH_MONGO=0}"
  ENV_COMMON="${ENV_COMMON},
    \"PUBLISH_MONGO\": \"1\",
    \"MONGO_URI\": $(jstr "$MONGO_URI"),
    \"DB_PASSWORD\": $(jstr "${DB_PASSWORD:-}"),
    \"MONGO_DB\": $(jstr "${MONGO_DB:-Top150}"),
    \"BUNDLE\": $(jstr "${BUNDLE:-top150}")"
else
  ENV_COMMON="${ENV_COMMON},
    \"PUBLISH_MONGO\": \"0\""
fi

# Last line of defence before the payload names a volume to mount.
if is_protected "$RUNPOD_VOLUME_ID"; then
  echo "REFUSING: pod payload would mount $RUNPOD_VOLUME_ID, a read-only data volume" >&2
  exit 2
fi
if [ "$RUNPOD_VOLUME_ID" = "$SRC_VOLUME_ID" ]; then
  echo "REFUSING: mount volume == source volume ($SRC_VOLUME_ID)" >&2
  exit 2
fi

if [ "$JOB" = "stage2" ]; then
  PAYLOAD=$(cat <<JSON
{
  "name": "investopediaclaude-predict-${JOB}",
  "computeType": "GPU",
  "cloudType": "SECURE",
  "gpuCount": 1,
  "gpuTypeIds": ${GPU_TYPES},
  "imageName": "${GPU_IMAGE}",
  "networkVolumeId": "${RUNPOD_VOLUME_ID}",
  "containerDiskInGb": ${RUNPOD_CONTAINER_DISK_GB:-40},
  "volumeMountPath": "/workspace",
  "dataCenterIds": ["${DC}"],
  "dockerStartCmd": ["bash", "/workspace/code/predict/bootstrap.sh"],
  "env": { "PIP_PACKAGES": "${PIP_GPU}", ${ENV_COMMON} }
}
JSON
)
else
  # Same body for CPU and for the GPU fallback — only the compute stanza differs.
  build_cpu_payload() {   # $1: "" for CPU, else a gpuTypeId
    local COMPUTE
    if [ -z "$1" ]; then
      COMPUTE="\"computeType\": \"CPU\", \"vcpuCount\": ${VCPU}, \"cpuFlavorIds\": ${FLAVORS}"
    else
      COMPUTE="\"computeType\": \"GPU\", \"gpuCount\": 1, \"gpuTypeIds\": [\"$1\"]"
    fi
    cat <<JSON
{
  "name": "investopediaclaude-predict-${JOB}",
  ${COMPUTE},
  "cloudType": "SECURE",
  "imageName": "${CPU_IMAGE}",
  "networkVolumeId": "${RUNPOD_VOLUME_ID}",
  "containerDiskInGb": ${CPU_DISK},
  "volumeMountPath": "/workspace",
  "dataCenterIds": ["${DC}"],
  "dockerStartCmd": ["bash", "/workspace/code/predict/bootstrap.sh"],
  "env": { "PIP_PACKAGES": "${PIP_CPU}", ${ENV_COMMON} }
}
JSON
  }
  PAYLOAD=$(build_cpu_payload "")
fi

# The payload must be valid JSON — a stray quote in a secret would otherwise
# surface as an opaque HTTP 400 from RunPod. DRY_RUN stops here, showing the
# pod's env with secrets redacted.
if ! printf '%s' "$PAYLOAD" | python3 -c '
import json, sys
p = json.load(sys.stdin)
if len(sys.argv) > 1:
    env = p["env"]
    for k in list(env):
        if any(s in k for s in ("KEY", "SECRET", "PASSWORD", "URI")) and env[k]:
            env[k] = "<redacted>"
    print(json.dumps(p, indent=2))
' ${DRY_RUN:+show}; then
  echo "pod payload is not valid JSON — check the env values (quotes?)" >&2
  exit 2
fi
if [ -n "${DRY_RUN:-}" ]; then
  echo "DRY_RUN: payload valid; would upload $(du -h "$TMP_TGZ" | cut -f1) bundle + bootstrap and launch the $JOB pod"
  rm -f "$TMP_TGZ"
  exit 0
fi
aws s3 cp $S3FLAGS "$TMP_TGZ" "$BUCKET/code/predict/bundle.tgz"
aws s3 cp $S3FLAGS "$REPO_ROOT/scripts/pod_bootstrap_predict.sh" "$BUCKET/code/predict/bootstrap.sh"
rm -f "$TMP_TGZ"

echo "Creating ${JOB} pod in ${DC} ..."
post_create() {
  RESP=$(curl -sS -w $'\n%{http_code}' -X POST https://rest.runpod.io/v1/pods \
    -H "Authorization: Bearer ${RUNPOD_API_KEY}" -H 'Content-Type: application/json' \
    -d "$PAYLOAD")
  CODE=$(printf '%s' "$RESP" | tail -n1); BODY=$(printf '%s' "$RESP" | sed '$d')
  [ "$CODE" = "200" ] || [ "$CODE" = "201" ]
}
if [ "$JOB" = "stage2" ]; then PLACED_ON="GPU (stage2 native)"; else PLACED_ON="CPU ${VCPU}vCPU"; fi
if ! post_create; then
  # stage2 genuinely wants its GPU image, so the fallback applies only to the CPU jobs.
  # Only a capacity refusal justifies it — a bad payload must still fail loudly.
  if [ "$JOB" != "stage2" ] && [ "$GPU_FALLBACK" = "1" ] && \
     printf '%s' "$BODY" | grep -q "no longer any instances\|no instances currently available"; then
    echo "  no CPU capacity in ${DC} — falling back to the cheapest available GPU" >&2
    OLDIFS="$IFS"; IFS='|'
    for G in $GPU_FALLBACK_TYPES; do
      IFS="$OLDIFS"; [ -n "$G" ] || continue
      echo "  trying GPU: $G" >&2
      PAYLOAD=$(build_cpu_payload "$G")
      if post_create; then PLACED_ON="GPU $G"; break; fi
      IFS='|'
    done
    IFS="$OLDIFS"
  fi
fi
if [ "$CODE" != "200" ] && [ "$CODE" != "201" ]; then
  echo "pod create failed (HTTP $CODE):" >&2; echo "$BODY" >&2
  [ "$GPU_FALLBACK" = "1" ] && echo "GPU fallback also found nothing free in ${DC}." >&2
  exit 1
fi
# Parse the TOP-LEVEL pod id. The old one-line sed was greedy (`.*"id"` matches the LAST
# "id" in the body), so a response carrying a nested networkVolume.id returned the VOLUME id
# instead of the pod id — observed 2026-08-27, when this printed 8qik4zxpxq for pod
# yqpva5puop0bwf. Anything downstream (watchdog, kill-and-retry) then targets a pod that does
# not exist and can duplicate a healthy running job.
POD_ID=$(printf '%s' "$BODY" | jq -r '.id // empty' 2>/dev/null)
[ -n "$POD_ID" ] || POD_ID=$(printf '%s' "$BODY" | \
  python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))' 2>/dev/null)
if [ -z "$POD_ID" ]; then
  echo "could not parse pod id from create response:" >&2; echo "$BODY" >&2; exit 1
fi
printf '%s\tpredict-%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$JOB" "$POD_ID" \
  >> "$ROOT/runpod/launched-pods.log"
echo "launched predict-${JOB} pod: ${POD_ID}  [${PLACED_ON}]"
echo "watch:   scripts/storage_usage.sh | grep -E '_pod_logs|derived'"
echo "fetch:   aws s3 cp \$S3FLAGS $BUCKET/derived/${JOB}/ ./derived_${JOB}/ --recursive"
