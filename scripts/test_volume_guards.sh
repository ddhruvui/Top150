#!/usr/bin/env bash
# Regression test for the volume contract: nothing this repo runs may write the
# data volume outside results/Top150. Hermetic — no network, no real aws, no pod.
#
#   scripts/test_volume_guards.sh
#
# Part 1 sources scripts/_common.sh in a scratch repo with a fake runpod/.env and a
# stub `aws` that records its argv, then checks src_s3 / res_s3 map or refuse.
# Part 2 runs scripts/pod_bootstrap_predict.sh against a fake volume (a temp dir
# standing in for /workspace, with data/ and a sibling project's results/), with
# stubbed python/aws/pip, and checks that the job's log, marker and outputs land
# under results/Top150 while data/ and the sibling stay byte-identical — and that a
# write path outside results/Top150 stops the job (ec=95) before it runs.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
_tmp="${TMPDIR:-/tmp}"; T=$(mktemp -d "${_tmp%/}/volguard.XXXXXX")
trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { pass=$((pass + 1)); echo "  ok   $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1"; }

# ---------------------------------------------------------------- part 1: S3 accessors
echo "--- part 1: src_s3 / res_s3"
mkdir -p "$T/repo/scripts" "$T/repo/runpod" "$T/bin"
cp "$REPO/scripts/_common.sh" "$T/repo/scripts/"
cat > "$T/repo/runpod/.env" <<'ENV'
AWS_ACCESS_KEY_ID=x
AWS_SECRET_ACCESS_KEY=x
RUNPOD_S3_REGION=eu-ro-1
RUNPOD_S3_ENDPOINT=https://s3.example
RUNPOD_VOLUME_ID=crimtr8kbf
ENV
cat > "$T/bin/aws" <<'SH'
#!/usr/bin/env bash
echo "$*" >> "$AWS_LOG"
SH
chmod +x "$T/bin/aws"
export AWS_LOG="$T/aws.log"

# run <expect: ok|refuse> <label> <command...> — each in a fresh shell
run() {
  local expect="$1" label="$2"; shift 2
  : > "$AWS_LOG"
  PATH="$T/bin:$PATH" bash -c '. "$1/scripts/_common.sh"; shift; "$@"' _ "$T/repo" "$@" >/dev/null 2>&1
  local rc=$?
  if [ "$expect" = ok ]; then
    [ $rc -eq 0 ] && [ -s "$AWS_LOG" ] && ok "$label" || bad "$label (rc=$rc, aws: $(cat "$AWS_LOG"))"
  else
    [ $rc -ne 0 ] && [ ! -s "$AWS_LOG" ] && ok "$label" || bad "$label (rc=$rc, aws ran: $(cat "$AWS_LOG"))"
  fi
}
last() { cat "$AWS_LOG"; }

run ok     "src_s3 ls a data path"                      src_s3 ls data/ohlcv/
run ok     "src_s3 cp data -> local"                    src_s3 cp data/ohlcv/AAPL.json /tmp/a.json --quiet
grep -q "s3://crimtr8kbf/data/ohlcv/AAPL.json /tmp/a.json --quiet" "$AWS_LOG" && ok "src_s3 maps bare path onto the volume" || bad "src_s3 mapping: $(last)"
run refuse "src_s3 cp local -> data (bare)"             src_s3 cp /tmp/a.json data/x.json
run refuse "src_s3 cp local -> data, flag trailing"     src_s3 cp /tmp/a.json data/x.json --quiet
run refuse "src_s3 cp data -> s3 dest"                  src_s3 cp data/x.json s3://crimtr8kbf/data/y.json
run refuse "src_s3 cp -> results (still a write)"       src_s3 cp /tmp/a.json s3://crimtr8kbf/results/Top150/x
run refuse "src_s3 rm"                                  src_s3 rm data/x.json
run refuse "src_s3 mv"                                  src_s3 mv data/x.json /tmp/x
run refuse "src_s3 sync dest bare"                      src_s3 sync m1 scratch
run refuse "src_s3 flags before paths"                  src_s3 cp --quiet /tmp/a data/x

run ok     "res_s3 ls (whole prefix)"                   res_s3 ls --recursive
grep -q "s3://crimtr8kbf/results/Top150/ --recursive" "$AWS_LOG" && ok "res_s3 ls defaults to results/Top150" || bad "res_s3 ls: $(last)"
run ok     "res_s3 cp local -> bare (results)"          res_s3 cp /tmp/b.tgz code/predict/bundle.tgz --only-show-errors
grep -q "/tmp/b.tgz s3://crimtr8kbf/results/Top150/code/predict/bundle.tgz" "$AWS_LOG" && ok "res_s3 maps bare dest under results/Top150" || bad "res_s3 mapping: $(last)"
run ok     "res_s3 cp results -> local"                 res_s3 cp _pod_logs/x.log /tmp/x.log --quiet
run ok     "res_s3 sync retired calc vol -> results"    res_s3 sync s3://k4cli3aj48/models/ models/
run ok     "res_s3 rm a results path"                   res_s3 rm derived/top150/tmp.json
run refuse "res_s3 cp -> s3://crimtr8kbf/data"          res_s3 cp /tmp/a s3://crimtr8kbf/data/x.json
run refuse "res_s3 cp -> volume root"                   res_s3 cp /tmp/a s3://crimtr8kbf/x
run refuse "res_s3 cp -> sibling project"               res_s3 cp /tmp/a s3://crimtr8kbf/results/InvestOpediaClaude/x
run refuse "res_s3 cp -> Top150 lookalike"              res_s3 cp /tmp/a s3://crimtr8kbf/results/Top150x/y
run refuse "res_s3 cp -> ../ escape"                    res_s3 cp /tmp/a s3://crimtr8kbf/results/Top150/../../data/x
run refuse "res_s3 cp -> bare x/../../ escape"           res_s3 cp /tmp/a derived/../../../data/x.json
run refuse "res_s3 cp data -> results (read via res)"   res_s3 cp s3://crimtr8kbf/data/x.json derived/x.json
run refuse "res_s3 rm data"                             res_s3 rm s3://crimtr8kbf/data/x.json
run refuse "res_s3 rm the prefix itself"                res_s3 rm s3://crimtr8kbf/results/Top150 --recursive
run refuse "res_s3 mv from retired vol (deletes it)"    res_s3 mv s3://k4cli3aj48/x derived/x
run refuse "res_s3 extra s3 arg after positionals"      res_s3 cp /tmp/a derived/x s3://crimtr8kbf/data/y
run refuse "res_s3 cp -> other bucket"                  res_s3 cp /tmp/a s3://k4cli3aj48/x
run refuse "CALC_VOLUME_ID still exported"              env CALC_VOLUME_ID=k4cli3aj48 bash -c ". '$T/repo/scripts/_common.sh'; aws s3 ls"

# ------------------------------------------------------- part 2: the pod bootstrap
echo "--- part 2: pod_bootstrap_predict.sh on a fake volume"
FV="$T/fv"                        # stands in for /workspace
SC="$T/scratch"                   # stands in for /scratch
OPT="$T/opt"                      # stands in for /opt (container disk)
mkdir -p "$FV/data/ohlcv" "$FV/m1" "$FV/results/InvestOpediaClaude" "$FV/results/Top150/code/predict" "$T/pbin"
echo '[{"date":"2026-09-16"}]' > "$FV/data/ohlcv/AAPL.json"
echo m1 > "$FV/m1/sessions.parquet"
echo sibling > "$FV/results/InvestOpediaClaude/keep.txt"
snapshot() { (cd "$FV" && find data m1 results/InvestOpediaClaude -type f -exec shasum {} \; | sort; \
              find . -path ./results/Top150 -prune -o -print | sort); }
BEFORE=$(snapshot)

# The code bundle: a stand-in tree with tools/pod_publish.sh absent (publish is not under test).
mkdir -p "$T/code/src" && echo "print('job')" > "$T/code/src/job.py"
tar czf "$FV/results/Top150/code/predict/bundle.tgz" -C "$T/code" src

# Path-rewritten copy of the bootstrap: /workspace, /scratch, /opt/top150 -> temp dirs.
sed -e "s#/workspace#$FV#g" -e "s#/scratch#$SC#g" -e "s#/opt/top150#$OPT/top150#g" \
  "$REPO/scripts/pod_bootstrap_predict.sh" > "$T/bootstrap.sh"

# Stubs. `python -m src.pipeline.*` / build_market simulate a job by writing into
# OUT_DIR, MODEL_DIR, LEDGER_PATH and MARKET_DIR — the paths a real job writes.
REAL_PY=$(command -v python3)
cat > "$T/pbin/python" <<SH
#!/usr/bin/env bash
case "\$1 \${2:-}" in
  "- "*) cat >/dev/null; echo "terminated (stub)"; exit 0 ;;   # self-terminate: never the network
  "-m pip"*) exit 0 ;;
  "-m src.pipeline."*|"src/data/build_market.py "*)
    mkdir -p "\$OUT_DIR" "\$MODEL_DIR" "\$(dirname "\$LEDGER_PATH")" "\$MARKET_DIR"
    echo out > "\$OUT_DIR/suggestions.json"; echo m > "\$MODEL_DIR/champion.json"
    echo l > "\$LEDGER_PATH"; echo w > "\$MARKET_DIR/_manifest.json"
    echo "SIMULATED JOB ran"; exit 0 ;;
  "-c import sys; print"*) echo "python stub"; exit 0 ;;
esac
exec "$REAL_PY" "\$@"
SH
cat > "$T/pbin/aws" <<'SH'
#!/usr/bin/env bash
# s3 sync/cp <src> <dst>: create the destination so the prefetch "succeeds"
for a in "$@"; do case "$a" in /*) mkdir -p "$a" 2>/dev/null ;; esac; done
exit 0
SH
cat > "$T/pbin/timeout" <<'SH'
#!/usr/bin/env bash
shift; exec "$@"
SH
printf '#!/bin/sh\nexit 0\n' > "$T/pbin/sleep"
printf '#!/bin/sh\necho 204\n' > "$T/pbin/curl"          # never the network
printf '#!/bin/sh\nexit 1\n' > "$T/pbin/nvidia-smi"
chmod +x "$T/pbin/"*

R="$FV/results/Top150"
boot() {   # boot <pod-id> [VAR=value ...] — runs the bootstrap, prints its output
  local pod="$1"; shift
  env -i HOME="$T" PATH="$T/pbin:/usr/bin:/bin:/usr/sbin:/sbin" TMPDIR="$T" \
    RUNPOD_POD_ID="$pod" RUNPOD_TERMINATE_KEY=x JOB=predict USE_MARKET=1 PUBLISH_MONGO=0 \
    SRC_VOLUME_ID=crimtr8kbf RUNPOD_S3_ENDPOINT=https://s3.example RUNPOD_S3_REGION=eu-ro-1 \
    MARKET_DIR="$R/m1x150" OUT_DIR="$R/derived/top150/predict" \
    SCORES_DIR="$R/derived/top150/stage2" SCORES_DIR_ALT="$R/derived/top150/stage1" \
    LEDGER_PATH="$R/ledger/trials.parquet" MODEL_DIR="$R/models" \
    "$@" bash "$T/bootstrap.sh" 2>&1
}

out=$(boot podA); [ -n "${DEBUG:-}" ] && echo "$out"
echo "$out" | grep -q "SIMULATED JOB ran" && ok "good wiring: job runs" || bad "good wiring: job did not run
$out"
echo "$out" | grep -q "^job=0" && ok "good wiring: job=0" || bad "good wiring: no job=0"
ls "$R/_pod_logs/"*-predict-predict-podA.log >/dev/null 2>&1 && ok "log under results/Top150/_pod_logs" || bad "log not under results/Top150"
[ -f "$R/_pod_logs/.ran-podA" ] && ok "restart marker under results/Top150" || bad "marker missing"
[ -f "$R/derived/top150/predict/suggestions.json" ] && [ -f "$R/models/champion.json" ] \
  && [ -f "$R/ledger/trials.parquet" ] && [ -f "$R/m1x150/_manifest.json" ] \
  && ok "outputs under results/Top150" || bad "outputs missing under results/Top150"
[ -d "$OPT/top150/src_predict/src" ] && ok "code unpacked on container disk" || bad "code not on container disk"
[ ! -e "$FV/predict_src_predict" ] && ok "no code dir on the volume root" || bad "code dir on the volume root"

out=$(boot podA); [ -n "${DEBUG:-}" ] && echo "$out"
echo "$out" | grep -q "RESTART DETECTED" && ok "restart of the same pod does not re-run" || bad "restart re-ran"

for bad_case in "MODEL_DIR=$FV/models" "OUT_DIR=$FV/data/derived" "LEDGER_PATH=$R/../../data/trials.parquet" \
                "MARKET_DIR=$FV/m1x" "SCORES_DIR=$FV/derived/stage2" "OUT_DIR=$FV/results/InvestOpediaClaude/x"; do
  pod="pod$(echo "$bad_case" | shasum | cut -c1-8)"
  out=$(boot "$pod" "$bad_case")
  if echo "$out" | grep -q "FATAL: path outside the contract" && echo "$out" | grep -q "^job=95" \
     && ! echo "$out" | grep -q "SIMULATED JOB ran"; then ok "refused: ${bad_case#"$T"/}"
  else bad "not refused: $bad_case
$out"; fi
done

# A symlink planted inside results/Top150 that points at data/ must not pass.
ln -s "$FV/data" "$R/escape"
out=$(boot podSym "OUT_DIR=$R/escape/derived")
echo "$out" | grep -q "^job=95" && ok "refused: symlink out of results/Top150" || bad "symlink escape not refused
$out"
rm "$R/escape"

# No mounted data volume -> refuse, write nothing.
mv "$FV/data" "$FV/data.off"
out=$(boot podNoVol)
echo "$out" | grep -q "^job=95" && ok "refused: /workspace is not the data volume" || bad "unmounted volume not refused"
mv "$FV/data.off" "$FV/data"

AFTER=$(snapshot)
[ "$BEFORE" = "$AFTER" ] && ok "data/, m1/, sibling results and the volume root unchanged" \
  || bad "volume outside results/Top150 changed:
$(diff <(echo "$BEFORE") <(echo "$AFTER"))"

echo "--- $pass passed, $fail failed"
[ "$fail" -eq 0 ]
