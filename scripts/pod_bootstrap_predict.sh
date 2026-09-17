#!/usr/bin/env bash
# Prediction-stack pod entrypoint. HARD RULE: control ALWAYS reaches the
# self-termination block — a bare `exit` before it caused a crash-restart
# billing loop (RunPod restarts the container when dockerStartCmd exits).
# A per-pod marker on the volume makes restarts terminate instead of re-running.
#
# VOLUME CONTRACT. /workspace is crimtr8kbf — the one data volume. Its root (data/,
# m1/, m1x/, ...) belongs to a SEPARATE download system and is never written from
# here. EVERYTHING this pod writes goes under RESULTS_DIR: its log and restart
# marker, m1x105, derived, models, ledger, reports. Enforced below, not by habit:
#   - the code bundle unpacks onto CONTAINER disk and the job runs from there, so a
#     relative path can never land on the volume;
#   - every input path is a /scratch copy pulled by read-only S3 GETs — the job
#     never opens a file under /workspace/data or /workspace/m1;
#   - every write path is resolved (symlinks included) and must sit under
#     RESULTS_DIR, or the job does not run (ec=95).
set +e
RESULTS_DIR="/workspace/results/Core105"      # == VOL_RESULTS in scripts/_common.sh
VOLUME_OK=1
# Stat only: proves the data volume is what is mounted (a missing mount would make
# /workspace a container dir and every output would vanish with the pod).
if [ ! -d /workspace/data ] || [ ! -d /workspace/results ]; then
  VOLUME_OK=0
  BOOT_LOG_DIR="/tmp/_pod_logs"
else
  BOOT_LOG_DIR="$RESULTS_DIR/_pod_logs"
fi
mkdir -p "$BOOT_LOG_DIR" 2>/dev/null
BOOT_LOG="$BOOT_LOG_DIR/$(date -u +%Y%m%dT%H%M%SZ)-predict-${JOB:-stage1}-${RUNPOD_POD_ID:-nopod}.log"
exec > >(tee -a "$BOOT_LOG") 2>&1
echo "predict bootstrap $(date -u +%FT%TZ) pod=${RUNPOD_POD_ID:-?} job=${JOB:-stage1} results=$RESULTS_DIR"

MARKER="$BOOT_LOG_DIR/.ran-${RUNPOD_POD_ID:-nopod}"
ec=98
if [ "$VOLUME_OK" != "1" ]; then
  echo "FATAL: /workspace is not the data volume (no data/ or results/) — refusing to run"
  ec=95
elif [ -f "$MARKER" ]; then
  echo "RESTART DETECTED (marker $MARKER exists) — skipping job, terminating"
else
  touch "$MARKER" 2>/dev/null
  python -c 'import sys; print("python", sys.version)'
  nvidia-smi 2>/dev/null | head -12 || echo "(no GPU)"

  # Container disk, never the volume: per-pod, so concurrent pods cannot delete
  # each other's code, and no relative write from the job can reach /workspace.
  WORKDIR="/opt/core105/src_${JOB:-stage1}"
  case "$WORKDIR" in /workspace/*) echo "FATAL: code must not unpack onto the volume"; WORKDIR="" ;; esac
  if [ -n "$WORKDIR" ] && rm -rf "$WORKDIR" && mkdir -p "$WORKDIR" && cd "$WORKDIR" && \
     tar xzf "$RESULTS_DIR/code/predict/bundle.tgz" --no-same-owner -m; then
    echo "bundle unpacked: $(find . -name '*.py' | wc -l) py files"
    command -v apt-get >/dev/null && { apt-get update -qq && \
      apt-get install -y -qq libgomp1 curl >/dev/null 2>&1 || echo "!! libgomp1/curl install failed"; }
    PIP="${PIP_PACKAGES:-pandas pyarrow numpy PyYAML scipy lightgbm scikit-learn}"
    echo "pip install: $PIP"
    timeout 1200 python -m pip install --quiet --no-input --disable-pip-version-check $PIP \
      || echo "!! pip install failed — job will report missing imports"

    # ---- source prefetch: READ-ONLY GETs from the data volume ----------------
    # The data volume is also mounted at /workspace, but inputs are NOT read from
    # the mount: they are pulled STRICTLY via S3 GETs into container-local
    # /scratch, a consistent snapshot even if the download system rewrites the
    # tape mid-run. Every aws call below runs source -> /scratch; there is
    # deliberately no call in the reverse direction anywhere in this file.
    # Inputs are pulled per job and the env is re-pointed at /scratch.
    PREFETCH_FAIL=""
    if [ -z "${SRC_VOLUME_ID:-}" ]; then
      echo "FATAL: SRC_VOLUME_ID unset — refusing to run."
      echo "  Without it there is no /scratch snapshot to compute on. Launch through"
      echo "  scripts/launch_core105.sh, which always wires the read-only source."
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
          MEM="${MARKET_DIR:-$RESULTS_DIR/m1x105}/universe_membership.parquet"
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
    fi
    # ---- inputs: /scratch only -----------------------------------------------
    # Pinned for EVERY job, including the ones that do not prefetch a given tree.
    # A path left to its code default would now resolve onto the mounted data
    # volume and silently change what the job reads — e.g. build_market.py folds
    # NASDAQ_DIR/SP500 into the workset when that file exists, and it never did on
    # the old calc volume. A /scratch path that was not fetched stays absent, which
    # is exactly the behaviour the book has been computed under.
    export M1_DIR=/scratch/m1 EOD_DIR=/scratch/data
    export NASDAQ_DIR=/scratch/data_nasdaq EOD_BULK_DIR=/scratch/data/eod_bulk/US
    export FINBERT_DIR="${FINBERT_DIR:-/scratch/data_finbert}"
    # ---- outputs: RESULTS_DIR only -------------------------------------------
    export MARKET_DIR="${MARKET_DIR:-$RESULTS_DIR/m1x105}"
    export OUT_DIR="${OUT_DIR:-$RESULTS_DIR/derived/${JOB:-stage1}}"
    export SCORES_DIR="${SCORES_DIR:-$RESULTS_DIR/derived/stage2}"
    export SCORES_DIR_ALT="${SCORES_DIR_ALT:-$RESULTS_DIR/derived/stage1}"
    # G-09: one ledger for ALL runs — a per-pod ledger would undercount DSR's N
    export LEDGER_PATH="${LEDGER_PATH:-$RESULTS_DIR/ledger/trials.parquet}"
    # continual learning: champions persist here between daily predict runs. Always
    # set: predict otherwise falls back to the config's /workspace/models, which on
    # this mount is the volume root.
    export MODEL_DIR="${MODEL_DIR:-$RESULTS_DIR/models}"
    export BUNDLE_OUT="$RESULTS_DIR/reports/${BUNDLE:-core105}"
    export REFIT="${REFIT:-auto}"
    GUARD_FAIL=""
    for k in M1_DIR EOD_DIR NASDAQ_DIR EOD_BULK_DIR FINBERT_DIR MARKET_PRICES_DIR ENTITIES_PATH; do
      [ -n "${!k:-}" ] || continue
      case "${!k}/" in /scratch/?*) ;; *) GUARD_FAIL="$GUARD_FAIL $k=${!k}(input-not-scratch)" ;; esac
    done
    # Both sides resolved (symlinks included), so neither a link planted under
    # results/Core105 nor a '..' can carry a write path out of it.
    realp() { python -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$1" 2>/dev/null; }
    RESULTS_REAL=$(realp "$RESULTS_DIR")
    [ -n "$RESULTS_REAL" ] || GUARD_FAIL="$GUARD_FAIL RESULTS_DIR(unresolvable)"
    for k in MARKET_DIR OUT_DIR SCORES_DIR SCORES_DIR_ALT LEDGER_PATH MODEL_DIR BUNDLE_OUT; do
      real=$(realp "${!k}")
      case "$real/" in "${RESULTS_REAL:-/nonexistent}"/?*) ;; *) GUARD_FAIL="$GUARD_FAIL $k=${!k}(->${real:-?})" ;; esac
    done
    if [ -z "$PREFETCH_FAIL" ] && [ -n "$GUARD_FAIL" ]; then
      echo "FATAL: path outside the contract —$GUARD_FAIL"
      echo "  inputs must be /scratch copies; outputs must resolve under $RESULTS_DIR."
      echo "  Refusing to run: nothing on the data volume outside results/Core105 is writable from here."
      ec=95
    elif [ -z "$PREFETCH_FAIL" ]; then
      echo "paths OK: inputs /scratch, outputs under $RESULTS_DIR"
      mkdir -p "$OUT_DIR"

      case "${JOB:-stage1}" in
        test)    timeout 3600  python -m pytest tests/ -q ;;
        market)  timeout 28800 python src/data/build_market.py ;;
        stage1)  timeout 28800 python -m src.pipeline.stage1 --m1 "$M1_DIR" --eod "$EOD_DIR" \
                   --out "$OUT_DIR" ${USE_MARKET:+--market "$MARKET_DIR"} ;;
        stage2)  timeout 64800 python -m src.pipeline.stage2 --m1 "$M1_DIR" --eod "$EOD_DIR" \
                   --out "$OUT_DIR" ${USE_MARKET:+--market "$MARKET_DIR"} ;;
        stage3)  timeout 28800 python -m src.pipeline.stage3 --m1 "$M1_DIR" --eod "$EOD_DIR" \
                   --out "$OUT_DIR" --scores "$SCORES_DIR" \
                   ${USE_MARKET:+--market "$MARKET_DIR"} ${NO_CPCV:+--no-cpcv} ;;
        exp)     timeout 28800 python -m src.pipeline.experiments --m1 "$M1_DIR" \
                   --eod "$EOD_DIR" --out "$OUT_DIR" \
                   --scores "$SCORES_DIR" \
                   --scores-alt "$SCORES_DIR_ALT" \
                   ${USE_MARKET:+--market "$MARKET_DIR"} ;;
        predict) timeout 14400 python -m src.pipeline.predict --m1 "$M1_DIR" --eod "$EOD_DIR" \
                   --out "$OUT_DIR" ${USE_MARKET:+--market "$MARKET_DIR"} ;;
        *) echo "unknown JOB '$JOB'" ;;
      esac
      ec=$?

      # ---- publish: bundle + MongoDB straight from this pod ---------------------
      # The deployed UI reads MongoDB, so nothing has to be pulled to a laptop.
      #   predict -> book mode:     G-02 (read-only LIST of the source), all sections
      #   stage3  -> research mode: gates/equity/ledger only; the book is untouched
      # Gated on job=0: a failed or watchdog-killed job must never publish.
      PUB_MODE=""
      case "${JOB:-stage1}" in predict) PUB_MODE=book ;; stage3) PUB_MODE=research ;; esac
      if [ -n "$PUB_MODE" ] && [ "$ec" -eq 0 ]; then
        if [ "${PUBLISH_MONGO:-1}" = "1" ] && [ -n "${MONGO_URI:-}" ]; then
          PUBLISH_MODE="$PUB_MODE" BUNDLE="${BUNDLE:-core105}" \
            BUNDLE_OUT="$BUNDLE_OUT" bash tools/pod_publish.sh
          pub=$?
          case "$pub" in
            0) echo "publish=0 ($PUB_MODE PUBLISHED — deployed UI updates within ~30 s)" ;;
            3) echo "publish=3 (G-02 FAIL — stale close, NOT published; rerun market + predict)" ;;
            *) echo "publish=$pub (FAILED — output intact on the volume; mirror_core105.sh publishes it)" ;;
          esac
        else
          echo "publish=skipped (PUBLISH_MONGO=${PUBLISH_MONGO:-1}, MONGO_URI $([ -n "${MONGO_URI:-}" ] && echo set || echo unset))"
        fi
      fi
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
        if st in (200, 202, 204): print(f"terminated ({st})"); sys.exit(0)
        print("terminate: unexpected status", st, file=sys.stderr)
    except urllib.error.HTTPError as e:
        if e.code == 404: print("already gone (404)"); sys.exit(0)
        # 2026-09-07: this branch used to swallow the code silently, so a 401/429/5xx
        # looked like "not confirmed" 12 times over and the pod restarted into a
        # billing loop. Say what came back.
        print("terminate: HTTP", e.code, (e.read() or b"")[:200], file=sys.stderr)
    except Exception as e:
        print("terminate error:", e, file=sys.stderr)
sys.exit(1)
PY
  [ $? -eq 0 ] && exit 0
  # second path: curl (installed above) — independent of python's SSL/cert state
  if command -v curl >/dev/null; then
    code=$(curl -sS --max-time 30 -o /dev/null -w '%{http_code}' -X DELETE \
      "https://rest.runpod.io/v1/pods/${RUNPOD_POD_ID:-}" \
      -H "Authorization: Bearer ${RUNPOD_TERMINATE_KEY:-}" 2>/dev/null)
    case "$code" in 200|202|204|404) echo "terminated via curl ($code)"; exit 0 ;;
                    *) echo "terminate via curl: HTTP $code" ;; esac
  fi
  echo "terminate attempt $attempt not confirmed — retry in 20s"; sleep 20
done
echo "!! TERMINATION NOT CONFIRMED — run scripts/killpod.sh"
sleep 30
