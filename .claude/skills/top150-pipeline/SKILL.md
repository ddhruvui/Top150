---
name: top150-pipeline
description: Run and monitor the TOP-150 pipeline — the daily loop (market → predict → reports/top150 bundle) and the quarterly research refresh (stage1 → stage2 GPU → stage3 → FULL_MIRROR) — on the one data volume crimtr8kbf, writing only under results/Top150 and reading everything else (data/, m1/, m1x/) strictly read-only. Use this whenever the user asks to run the top150 daily or quarterly steps, refresh the book/suggestions/reports, rerun stage1/2/3, or check on pods. This repo does NOT download data: a separate system fills crimtr8kbf, and verify_source.py is the gate that says whether it has finished. The volume contract is not visible from the scripts themselves.
---

# Top-150 pipeline: daily and quarterly

This repo **computes; it does not ingest.** There is no vendor-download code here and
there must never be any again — a separate system owns every fetch that fills the
source tape. **One volume, `crimtr8kbf`** (since 2026-09-17; the old calc volume
`k4cli3aj48` is retired), and the split *inside* it is the whole safety model:

- **The root — `data/`, `m1/`, `m1x/`, `data_*`** — the data **SOURCE**, owned by the
  download system. **STRICTLY READ-ONLY.** Pods mount the volume at `/workspace` but do
  not read inputs from the mount: they pull them via S3 GETs into container-local
  `/scratch` (the prefetch block in `pod_bootstrap_predict.sh`).
  Vendor layout under `data/`: per-ticker EODHD OHLCV at `ohlcv/<TICKER>.json` (no
  `.US` suffix; moved from `data/<TICKER>.json` by the 2026-09-17 run), SPY at
  `market/SPY.US.json`, whole-exchange day-files at `eod_bulk/US/<DATE>.json`, plus
  `news/`, `dividends/`, `splits/`, `fundamentals/`, `estimates/` keyed by ticker.
  The pipeline itself prices off the parsed `m1/` and `m1x/` trees, not these files.
- **`results/Top150/`** — everything this repo writes, and the only place it writes:
  `m1x150/`, `derived/top150/*`, `models/`, `ledger/`, `reports/`, `code/`,
  `_pod_logs/`. Same relative layout the calc volume had
  (`k4cli3aj48:/X` == `crimtr8kbf:/results/Top150/X`). `results/InvestOpediaClaude/`
  and `results/ResearchGate/` are other projects' — never touched.

`scripts/launch_top150.sh <market|test|stage1|stage2|stage3|predict|exp>` sets the
wiring (`UNIVERSE_SIZE=150`, `MARKET_DIR=/workspace/results/Top150/m1x150`,
`SYSTEM_CONFIG=configs/system_top150.yaml`,
`OUT_DIR=/workspace/results/Top150/derived/top150/<job>`) and hands off to
`launch_predict.sh`.

**The contract is enforced in code, in layers** — you do not have to remember it, but do
not work around it either. `scripts/test_volume_guards.sh` proves each one (hermetic,
no network; run it after touching any of these files):

1. `scripts/_common.sh` pins `RESULTS_PREFIX=results/Top150` and exposes the only two
   S3 accessors: `src_s3` (read-only: `ls`/`cp`/`sync`, destination must be local disk)
   and `res_s3` (the only writer: every destination, `rm` and `mv` must resolve under
   `results/Top150`, `..` refused). Paths first, flags after. It refuses a shell that
   still exports `CALC_VOLUME_ID`/`RUNPOD_VOLUME_ID_OVERRIDE`, and the retired volumes
   (`k4cli3aj48`, `8qik4zxpxq`) as a mount.
2. `scripts/launch_predict.sh` refuses any pod path (`OUT_DIR`, `MARKET_DIR`,
   `MODEL_DIR`, `LEDGER_PATH`, `SCORES_DIR*`) outside `/workspace/results/Top150`, and
   uploads the code bundle through `res_s3`.
3. `scripts/pod_bootstrap_predict.sh` refuses to run (`ec=95`) unless `/workspace` is
   the data volume, every input is a `/scratch` path, and every write path resolves —
   symlinks included — under `results/Top150`. The code unpacks onto container disk
   (`/opt/top150`), so a relative write can never reach the volume. It still **aborts
   on an incomplete prefetch** (`ec=96`).
4. **Do not edit `configs/*.yaml` to change paths — not even comments.** `config_hash`
   is the SHA-256 of the file's bytes: any edit forces a full refit and orphans the
   stage artifacts. The pods override the config's `/workspace/models` etc. through
   env vars instead.

Bundled helpers in `.claude/skills/top150-pipeline/scripts/` (call by full path;
`SK150=.claude/skills/top150-pipeline/scripts`):

| script | what it does |
|---|---|
| `verify_source.py` | **read-only gate**: has the separate download system finished? Reads each vendor tree's `_run.json` on the source. Exit 0 only if every tree is fresh with zero hard failures |
| `srcvol` | READ-ONLY `aws s3` against the volume root — `srcvol ls data/eod_bulk/US/`. Refuses `rm`/`mv`; a `cp`/`sync` destination must be a local path |
| `vol150` | `aws s3` against `results/Top150` (bare paths are relative to it) — `vol150 ls derived/top150/predict/`. Cannot write, move or delete outside it |
| `podlog150 <pat> [n]` | newest matching `results/Top150/_pod_logs/` entry |
| `pods` | account-wide pod list (name, id, status, created). Top150 pods are `top150-predict-<job>`; `investopediaclaude-*` and `researchgate-*` pods share the account and the volume and are **not ours — never delete them** |
| `watch_pods.py` | report-only watchdog over `top150-predict-*` pods; one line per state change (UP/DONE/STALL/IDLE) |
| `mirror_top150.sh` | laptop path (optional since the pod publishes): pull book (+stage artifacts with `FULL_MIRROR=1`), enforce G-02 vs the source tape, rebuild `reports/top150` for the git record, re-publish to MongoDB (`PUBLISH_MONGO=0` skips) |

## Hard rules (each one has burned a run)

1. **Never write to crimtr8kbf outside `results/Top150`.** Reads go through `src_s3` /
   `srcvol`, writes through `res_s3` / `vol150`. If you find yourself reaching for a raw
   `aws s3` against the volume, stop.
2. **Never add fetch/download/ingest code to this repo.** If data is missing or stale,
   that is the other system's job — report it, do not fetch it here. There is no
   `data_acquisition/`, no `daily.sh`, and no `watch_jobs.sh` any more; the last of
   those auto-relaunched jobs with prod wiring and would write the source tape.
3. **Branch check first**: `git branch --show-current` must say `top150` (or `top200`).
   The backend serves the bundle named by `BUNDLE` (default `top150`) — from MongoDB
   when `MONGO_URI` is set, else `reports/<bundle>` on disk.
4. A launched pod with **no bootstrap log in `results/Top150/_pod_logs` within ~5 min** is on a broken
   EU-RO-1 host (struck twice on 2026-09-01): it bills forever while RUNNING and never
   starts. Check `$SK150/vol150 ls _pod_logs/ | tail`, then DELETE the pod
   (`KILL_IDS=<id> scripts/killpod.sh`) and relaunch. `launch_predict.sh` does not
   verify startup. Apply this only to a `top150-predict-*` pod id you launched.
5. **A pod exiting is not success.** Only `job=0` in the log is. A stage can be
   OOM-killed (`exit=-9`) while its pod self-terminates normally, leaving yesterday's
   output in place.
6. **`job=0` is not "pod gone" either.** On 2026-09-07 two finished pods logged
   `terminate attempt N not confirmed` twelve times, exited, were restarted by RunPod,
   hit the marker (`job=98`) and looped — billing all the while. After a `job=` line,
   confirm the pod left `$SK150/pods`; if not, `scripts/killpod.sh` (curl DELETE; the
   laptop's python has no CA bundle). The bootstrap now prints the DELETE's HTTP status
   and retries via curl.
   Root cause (seen in the log 2026-09-08): RunPod's REST API answers the pod's
   python `urllib` DELETE with a Cloudflare **403 "error code: 1010"** (blocked by
   the client signature); curl gets a 204. The bootstrap now falls back to curl.
8. **One pod at a time when the ledger is being written.** The G-09 trials ledger
   (`/workspace/results/Top150/ledger/trials.parquet`) is rewritten whole on every append; a second
   pod reading it mid-write sees a 0-byte parquet and dies (`ArrowInvalid: Parquet
   file size is 0 bytes` — an `exp` pod launched 30 s after `predict`, 2026-09-08).
   Run predict/stage/exp jobs sequentially, or at least not within the same minute.
9. **Experiment output stays out of `derived/top150/`.** Branch `exp-short-horizon`
   writes to `OUT_DIR=/workspace/results/Top150/derived/exp_short/<job>` and
   launches with `PUBLISH_MONGO=0`; the production prefixes are the daily loop's.

## Daily loop

**Prerequisite — the source tape must be complete for the session.** The `market` job
does not parse `eod_bulk` itself: the prefetch pulls the already-parsed
`m1x/market_prices` parts + `m1/entities.parquet` and sets `SKIP_BULK=1`; `predict`
pulls the whole `m1/` tree. A stale or partially-filled source ⇒ a stale book. Gate on
it first, and if it fails, say so rather than trying to fix the source:

```sh
.claude/skills/top150-pipeline/scripts/verify_source.py   # all FRESH, fail=0
```

> EODHD's bulk day-file keeps FILLING for hours after it first appears (measured
> 2026-09-03: a 01:30 UTC snapshot froze 35k rows with real S&P names missing, AAPL
> included; the complete ~44k-row file wasn't there until ~02:50 UTC). `verify_source.py`
> checks manifests, not row counts — if the book later looks wrong, suspect this.

Then, in order (each: launch → confirm bootstrap log → wait → verify exit):

```sh
scripts/launch_top150.sh market     # membership@150 + workset -> results/Top150/m1x150
scripts/launch_top150.sh predict    # book -> results/Top150/derived/top150/predict
```

After each launch confirm `$SK150/vol150 ls _pod_logs/ | tail -2` shows a fresh
`predict-<job>-<podid>.log` (rule 4 if not). After each pod self-terminates, require
`job=0` in `$SK150/podlog150 predict-<job>`. The champion store and trials ledger live
under `results/Top150` (`models/`, `ledger/`), so a full refit instead of a warm update
is normal on fresh history — and on the first run after the move if the calc volume's
`models/` and `ledger/` were not copied across.

**Publishing happens on the pod.** When `predict` exits `job=0`, the same pod runs
`tools/pod_publish.sh`: it enforces **G-02** (`as_of_close` must equal the newest
`data/eod_bulk/US/` day-file **on the source** — a read-only LIST), builds the bundle
with `tools/build_reports.py` (predict output + the stage1/2/3 artifacts under
`results/Top150` + the session grid from the prefetch), writes it to
`/workspace/results/Top150/reports/top150`,
and publishes it to MongoDB (`Top150` db). The deployed UI (Render → Vercel API) shows
it within ~30 s. Nothing is downloaded to a laptop. The launcher passes the Mongo
credentials from the repo-root `.env` into the predict pod; `PUBLISH_MONGO=0` launches
without them.

Read the outcome from the pod log, below the `job=` line:

| line | meaning |
|---|---|
| `publish=0` | published — done |
| `publish=3` | **G-02 FAIL**: the book priced a stale close. Rerun market + predict; nothing was published |
| `publish=<other>` | build or publish error; the predict output is intact on the volume — `mirror_top150.sh` publishes it from the laptop |
| `publish=skipped` | launched with `PUBLISH_MONGO=0` or no `MONGO_URI` |

`mirror_top150.sh` is now optional: it pulls the artifacts, rebuilds `reports/top150`
locally (the git record) and re-publishes — same G-02, same content.

View: the deployed UI — see `DEPLOY.md`. Locally: `scripts/serve_top150_console.sh`
(:8790, files) or `app/backend && npm start` (Mongo via `.env`).

## Quarterly research refresh (stage1 → stage2 → stage3)

Run after config/code changes or on the quarterly cadence:

```sh
scripts/launch_top150.sh stage1     # LGBM walk-forward + gates (CPU, hours)
scripts/launch_top150.sh stage2     # GRU+CNN+FinBERT (GPU)
scripts/launch_top150.sh stage3     # meta gate + barrier book + CPCV
```

- Run them **in order**; confirm each pod's bootstrap log (rule 4), then `job=0` via
  `podlog150` before launching the next. `launch_top150.sh` already points
  `SCORES_DIR`/`SCORES_DIR_ALT` at the top150 stage dirs for stage3.
- **stage2 "no instances available" 500**: WIDEN the GPU pool — the 3-type default is
  the constraint, not disk. `RUNPOD_GPU_TYPES` with ~9 card types fixed it instantly
  on 2026-09-01, e.g.:
  `RUNPOD_GPU_TYPES='["NVIDIA GeForce RTX 4090","NVIDIA RTX A5000","NVIDIA A40","NVIDIA RTX A4500","NVIDIA RTX A6000","NVIDIA GeForce RTX 3090","NVIDIA L4","NVIDIA RTX 4000 Ada Generation","NVIDIA L40S","NVIDIA RTX A4000"]' scripts/launch_top150.sh stage2`
  Every id must be in RunPod's current `gpuTypeIds` enum or the whole create is an
  HTTP 400 ("value must be one of …") — `NVIDIA A30` dropped out of it on 2026-09-07.
- **Interpreting results**: stage1 KILL is NOT diagnostic — the book only emerges at
  stage3. Known baseline (2026-09-01 full run): stage3 ungated 9.6% CAGR / SR 0.59 /
  MDD −45%; last-3y 13.3%/0.64; `lgbm_h5` degenerates on 150 names (valid RIC 0.0000
  every fold) and M10-03 admits only h20+h60.

**The stage3 pod publishes the research refresh itself** (`publish=0` in its log, below
`job=`): `tools/pod_publish.sh` in *research* mode rebuilds the bundle from the stage
artifacts under `results/Top150` and publishes the gates verdict, members, equity curve,
CPCV and trade ledger. It deliberately leaves the `suggestions` section untouched — the
book the UI shows is only ever written by a G-02-verified predict publish, so a research
refresh never re-pushes whatever `suggestions.json` sits on the volume. The next daily
predict then publishes a fresh book on top of the new research sections.

Optional, for the git record (the refreshed `derived/top150/` artifacts and
`reports/top150` are committed on this branch):

```sh
FULL_MIRROR=1 .claude/skills/top150-pipeline/scripts/mirror_top150.sh
```

## Monitoring

Start `watch_pods.py` under a Monitor (wrapped in `caffeinate -dims`), read logs with
`podlog150` before acting on a STALL, and never treat "pod gone" as success. Rough
runtimes from the 2026-09-01 run: market ~minutes, predict ~minutes (longer on
full-refit days), stage1 hours, stage2 the long pole (GPU), stage3 ~1-2 h.

## Reporting back

Per job: pod id, `job=0` (or the failing line), and for the daily loop the G-02 result
plus book size (`suggestions.json` n / as_of). For the quarterly loop: the stage3
verdict line, CPCV median, and whether the bundle + committed artifacts changed. If the
source tape was the blocker, say which trees were stale or failing — that is the other
system's problem to fix, not this one's.
