#!/usr/bin/env bash
# Prediction-stack pod entrypoint. HARD RULE: control ALWAYS reaches the
# self-termination block — a bare `exit` before it caused a crash-restart
# billing loop (RunPod restarts the container when dockerStartCmd exits).
# A per-pod marker on the volume makes restarts terminate instead of re-running.
set +e
BOOT_LOG_DIR="/workspace/_pod_logs"
mkdir -p "$BOOT_LOG_DIR" 2>/dev/null
BOOT_LOG="$BOOT_LOG_DIR/$(date -u +%Y%m%dT%H%M%SZ)-predict-${JOB:-stage1}-${RUNPOD_POD_ID:-nopod}.log"
exec > >(tee -a "$BOOT_LOG") 2>&1
echo "predict bootstrap $(date -u +%FT%TZ) pod=${RUNPOD_POD_ID:-?} job=${JOB:-stage1}"

MARKER="/workspace/_pod_logs/.ran-${RUNPOD_POD_ID:-nopod}"
ec=98
if [ -f "$MARKER" ]; then
  echo "RESTART DETECTED (marker $MARKER exists) — skipping job, terminating"
else
  touch "$MARKER" 2>/dev/null
  python -c 'import sys; print("python", sys.version)'
  nvidia-smi 2>/dev/null | head -12 || echo "(no GPU)"

  WORKDIR="predict_src_${JOB:-stage1}"        # per-job dir: concurrent pods share the volume
  cd /workspace && rm -rf "$WORKDIR" && mkdir "$WORKDIR" && cd "$WORKDIR"
  if tar xzf /workspace/code/predict/bundle.tgz --no-same-owner -m; then
    echo "bundle unpacked: $(find . -name '*.py' | wc -l) py files"
    command -v apt-get >/dev/null && { apt-get update -qq && \
      apt-get install -y -qq libgomp1 >/dev/null 2>&1 || echo "!! libgomp1 install failed"; }
    PIP="${PIP_PACKAGES:-pandas pyarrow numpy PyYAML scipy lightgbm scikit-learn}"
    echo "pip install: $PIP"
    timeout 1200 python -m pip install --quiet --no-input --disable-pip-version-check $PIP \
      || echo "!! pip install failed — job will report missing imports"

    # ---- source prefetch: READ-ONLY GETs from the data volume ----------------
    # The pod mounts the CALC volume at /workspace; the data volume is read
    # STRICTLY via S3 GETs into container-local /scratch — it is never mounted
    # and never written. Every aws call below runs source -> /scratch; there is
    # deliberately no call in the reverse direction anywhere in this file.
    # Inputs are pulled per job and the env is re-pointed at /scratch.
    PREFETCH_FAIL=""
    if [ -z "${SRC_VOLUME_ID:-}" ]; then
      echo "FATAL: SRC_VOLUME_ID unset — refusing to run."
      echo "  Without it this job reads /workspace (the CALC volume), which holds no"
      echo "  raw data, and would silently compute on nothing. Launch through"
      echo "  scripts/launch_top150.sh, which always wires the read-only source."
      PREFETCH_FAIL="SRC_VOLUME_ID unset"
    else
      echo "prefetch: s3://${SRC_VOLUME_ID} -> /scratch (read-only GETs)"
      timeout 600 python -m pip install --quiet --no-input --disable-pip-version-check awscli \
        || PREFETCH_FAIL="pip awscli"
      SRC="s3://${SRC_VOLUME_ID}"
      EP=(--endpoint-url "${RUNPOD_S3_ENDPOINT}" --region "${RUNPOD_S3_REGION:-eu-ro-1}")
      mkdir -p /scratch
      if [ "${JOB:-stage1}" = "market" ]; then
        timeout 7200 aws s3 sync "${EP[@]}" --only-show-errors \
          "$SRC/m1x/market_prices" /scratch/market_prices || PREFETCH_FAIL="market_prices"
        mkdir -p /scratch/m1
        timeout 600 aws s3 cp "${EP[@]}" --only-show-errors \
          "$SRC/m1/entities.parquet" /scratch/m1/entities.parquet || PREFETCH_FAIL="entities"
        export MARKET_PRICES_DIR=/scratch/market_prices SKIP_BULK=1 \
               ENTITIES_PATH=/scratch/m1/entities.parquet
      else
        timeout 3600 aws s3 sync "${EP[@]}" --only-show-errors \
          "$SRC/m1" /scratch/m1 --exclude 'qlib/*' || PREFETCH_FAIL="m1"
        timeout 1200 aws s3 sync "${EP[@]}" --only-show-errors \
          "$SRC/data/market" /scratch/data/market || PREFETCH_FAIL="data/market"
        export M1_DIR=/scratch/m1 EOD_DIR=/scratch/data
        if [ "${JOB:-stage1}" = "stage2" ]; then
          timeout 3600 aws s3 sync "${EP[@]}" --only-show-errors \
            "$SRC/data_finbert" /scratch/data_finbert --exclude 'logs/*' \
            || PREFETCH_FAIL="data_finbert"
          export FINBERT_DIR=/scratch/data_finbert
          # F9 news slice: only the workset tickers of this experiment's universe
          MEM="${MARKET_DIR:-/workspace/m1x}/universe_membership.parquet"
          if [ -f "$MEM" ]; then
            INC=()
            while IFS= read -r t; do [ -n "$t" ] && INC+=(--include "${t}.json"); done \
              < <(MEM="$MEM" python -c 'import os, pandas as pd
print("\n".join(sorted(pd.read_parquet(os.environ["MEM"])["ticker"].astype(str).unique())))')
            echo "prefetch news: ${#INC[@]} include patterns -> ~$((${#INC[@]}/2)) tickers"
            timeout 7200 aws s3 sync "${EP[@]}" --only-show-errors \
              "$SRC/data/news" /scratch/data/news --exclude '*' "${INC[@]}" \
              || PREFETCH_FAIL="news"
          else
            echo "!! no $MEM — F9 news slice skipped (run the market job first)"
          fi
        fi
      fi
      df -h /scratch | tail -1; du -sh /scratch/* 2>/dev/null
    fi

    # A half-synced /scratch is the dangerous case: the job runs, exits 0, and
    # produces a book priced off partial source data that looks entirely normal.
    # PREFETCH_FAIL was recorded above and, until now, never read.
    if [ -n "$PREFETCH_FAIL" ]; then
      echo "FATAL: prefetch incomplete ($PREFETCH_FAIL) — refusing to compute on"
      echo "  partial source data. Fix the source read and relaunch."
      ec=96
    else
      export M1_DIR="${M1_DIR:-/workspace/m1}"
      export EOD_DIR="${EOD_DIR:-/workspace/data}"
      export MARKET_DIR="${MARKET_DIR:-/workspace/m1x}"
      export OUT_DIR="${OUT_DIR:-/workspace/derived/${JOB:-stage1}}"
      # G-09: one ledger for ALL runs — a per-pod ledger would undercount DSR's N
      export LEDGER_PATH="${LEDGER_PATH:-/workspace/ledger/trials.parquet}"
      # continual learning: champions persist here between daily predict runs
      export MODEL_DIR="${MODEL_DIR:-/workspace/models}"
      export REFIT="${REFIT:-auto}"
      mkdir -p "$OUT_DIR"

      case "${JOB:-stage1}" in
        test)    timeout 3600  python -m pytest tests/ -q ;;
        market)  timeout 28800 python src/data/build_market.py ;;
        stage1)  timeout 28800 python -m src.pipeline.stage1 --m1 "$M1_DIR" --eod "$EOD_DIR" \
                   --out "$OUT_DIR" ${USE_MARKET:+--market "$MARKET_DIR"} ;;
        stage2)  timeout 64800 python -m src.pipeline.stage2 --m1 "$M1_DIR" --eod "$EOD_DIR" \
                   --out "$OUT_DIR" ${USE_MARKET:+--market "$MARKET_DIR"} ;;
        stage3)  timeout 28800 python -m src.pipeline.stage3 --m1 "$M1_DIR" --eod "$EOD_DIR" \
                   --out "$OUT_DIR" --scores "${SCORES_DIR:-/workspace/derived/stage2}" \
                   ${USE_MARKET:+--market "$MARKET_DIR"} ${NO_CPCV:+--no-cpcv} ;;
        exp)     timeout 28800 python -m src.pipeline.experiments --m1 "$M1_DIR" \
                   --eod "$EOD_DIR" --out "$OUT_DIR" \
                   --scores "${SCORES_DIR:-/workspace/derived/stage2}" \
                   --scores-alt "${SCORES_DIR_ALT:-/workspace/derived/stage1}" \
                   ${USE_MARKET:+--market "$MARKET_DIR"} ;;
        predict) timeout 14400 python -m src.pipeline.predict --m1 "$M1_DIR" --eod "$EOD_DIR" \
                   --out "$OUT_DIR" ${USE_MARKET:+--market "$MARKET_DIR"} ;;
        *) echo "unknown JOB '$JOB'" ;;
      esac
      ec=$?
    fi
  else
    echo "FATAL: bundle unpack failed — proceeding to terminate"
    ec=97
  fi
fi
echo "job=$ec ($([ $ec -eq 124 ] && echo 'WATCHDOG TIMEOUT' || echo 'exited')) at $(date -u +%FT%TZ)"
sync 2>/dev/null

[ "${KEEP_POD:-}" = "1" ] && { echo "KEEP_POD=1 — not terminating"; sleep infinity; }
for attempt in $(seq 1 12); do
  timeout 60 python - <<'PY'
import os, ssl, sys, urllib.error, urllib.request as u
pid = os.environ.get("RUNPOD_POD_ID", ""); key = os.environ.get("RUNPOD_TERMINATE_KEY", "")
if not pid or not key: sys.exit(2)
url = "https://rest.runpod.io/v1/pods/" + pid
for ctx in (None, ssl._create_unverified_context()):
    try:
        req = u.Request(url, method="DELETE"); req.add_header("Authorization", "Bearer " + key)
        st = u.urlopen(req, timeout=30, context=ctx).status
        if st == 204: print("terminated (204)"); sys.exit(0)
    except urllib.error.HTTPError as e:
        if e.code == 404: print("already gone (404)"); sys.exit(0)
    except Exception as e:
        print("terminate error:", e, file=sys.stderr)
sys.exit(1)
PY
  [ $? -eq 0 ] && exit 0
  echo "terminate attempt $attempt not confirmed — retry in 20s"; sleep 20
done
echo "!! TERMINATION NOT CONFIRMED — run scripts/killpod.sh"
sleep 30
