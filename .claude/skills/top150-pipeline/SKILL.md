---
name: top150-pipeline
description: Run and monitor the TOP-150 pipeline — the daily loop (market → predict → reports/top150 bundle) and the quarterly research refresh (stage1 → stage2 GPU → stage3 → FULL_MIRROR) — computing onto the k4cli3aj48 calc volume while reading crimtr8kbf strictly read-only. Use this whenever the user asks to run the top150 daily or quarterly steps, refresh the book/suggestions/reports, rerun stage1/2/3, or check on pods. This repo does NOT download data: a separate system fills crimtr8kbf, and verify_source.py is the gate that says whether it has finished. The volume contract is not visible from the scripts themselves.
---

# Top-150 pipeline: daily and quarterly

This repo **computes; it does not ingest.** There is no vendor-download code here and
there must never be any again — a separate system owns every fetch that fills the
source tape. Two volumes, and the split is the whole safety model:

- **`crimtr8kbf`** — the data **SOURCE**. **STRICTLY READ-ONLY**: never mounted, never
  written, never deleted from. Pods read it via S3 GETs into container-local
  `/scratch` (the prefetch block in `pod_bootstrap_predict.sh`).
- **`k4cli3aj48`** — the **CALC** volume, mounted by pods at `/workspace`. Everything
  computed here lands here and nowhere else: `m1x150/`, `derived/top150/*`,
  `models/`, `ledger/`, `_pod_logs/`.

`scripts/launch_top150.sh <market|test|stage1|stage2|stage3|predict|exp>` sets the
wiring (`UNIVERSE_SIZE=150`, `MARKET_DIR=/workspace/m1x150`,
`SYSTEM_CONFIG=configs/system_top150.yaml`, `OUT_DIR=/workspace/derived/top150/<job>`)
and hands off to `launch_predict.sh`.

**The contract is enforced in code, in three places** — you do not have to remember it,
but do not work around it either:

1. `scripts/_common.sh` rebinds the mountable volume to the calc volume, refuses any
   id in `PROTECTED_VOLUMES` (`crimtr8kbf`, `8qik4zxpxq`), and refuses calc == source.
   It also exposes `src_s3`, the only sanctioned source accessor: `ls`/`cp`/`sync`
   only, and never a destination inside the source bucket.
2. `scripts/launch_predict.sh` re-asserts both before building the pod payload — the
   one line that actually names a volume to mount.
3. `scripts/pod_bootstrap_predict.sh` refuses to run without read-only source wiring,
   and now **aborts on an incomplete prefetch** instead of computing on a half-synced
   `/scratch` (`ec=96`).

Bundled helpers in `.claude/skills/top150-pipeline/scripts/` (call by full path;
`SK150=.claude/skills/top150-pipeline/scripts`):

| script | what it does |
|---|---|
| `verify_source.py` | **read-only gate**: has the separate download system finished? Reads each vendor tree's `_run.json` on the source. Exit 0 only if every tree is fresh with zero hard failures |
| `srcvol` | READ-ONLY `aws s3` against the SOURCE volume — `srcvol ls data/eod_bulk/US/`. Refuses `rm`/`mv` and refuses a source-bucket destination |
| `vol150` | `aws s3` against the CALC volume — `vol150 ls derived/top150/predict/` |
| `podlog150 <pat> [n]` | newest matching `_pod_logs/` entry on the calc volume |
| `pods` | account-wide pod list (name, id, status, created) |
| `watch_pods.py` | report-only watchdog; one line per state change (UP/DONE/STALL/IDLE) |
| `mirror_top150.sh` | pull book (+stage artifacts with `FULL_MIRROR=1`), enforce G-02 vs the source tape, rebuild `reports/top150`, **publish it to MongoDB** (`tools/publish_mongo.py`; `PUBLISH_MONGO=0` skips) |

## Hard rules (each one has burned a run)

1. **Never write to crimtr8kbf, and never mount it.** Reads go through `src_s3` /
   `srcvol`. If you find yourself reaching for a raw `aws s3` against the source, stop.
2. **Never add fetch/download/ingest code to this repo.** If data is missing or stale,
   that is the other system's job — report it, do not fetch it here. There is no
   `data_acquisition/`, no `daily.sh`, and no `watch_jobs.sh` any more; the last of
   those auto-relaunched jobs with prod wiring and would write the source tape.
3. **Branch check first**: `git branch --show-current` must say `top150` (or `top200`).
   The backend serves the bundle named by `BUNDLE` (default `top150`) — from MongoDB
   when `MONGO_URI` is set, else `reports/<bundle>` on disk.
4. A launched pod with **no bootstrap log on k4cli3aj48 within ~5 min** is on a broken
   EU-RO-1 host (struck twice on 2026-09-01): it bills forever while RUNNING and never
   starts. Check `$SK150/vol150 ls _pod_logs/ | tail`, then DELETE the pod
   (`scripts/killpod.sh`) and relaunch. `launch_predict.sh` does not verify startup.
5. **A pod exiting is not success.** Only `job=0` in the log is. A stage can be
   OOM-killed (`exit=-9`) while its pod self-terminates normally, leaving yesterday's
   output in place.

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
scripts/launch_top150.sh market     # membership@150 + workset -> /workspace/m1x150
scripts/launch_top150.sh predict    # book -> /workspace/derived/top150/predict
```

After each launch confirm `$SK150/vol150 ls _pod_logs/ | tail -2` shows a fresh
`predict-<job>-<podid>.log` (rule 4 if not). After each pod self-terminates, require
`job=0` in `$SK150/podlog150 predict-<job>`. The champion store and trials ledger live
on the calc volume (`/workspace/models`, `/workspace/ledger`), so a full refit instead
of a warm update is normal on fresh history.

Finish by publishing:

```sh
.claude/skills/top150-pipeline/scripts/mirror_top150.sh
```

It pulls `suggestions.json`, enforces **G-02** (`as_of_close` must equal the newest
`data/eod_bulk/US/` day-file **on the source**), stages a flat src dir, rebuilds
`reports/top150`, and **publishes it to MongoDB** (`Top150` db — needs `.env` at the
repo root; `tools/publish_mongo.py` alone re-publishes an already-built bundle). If
G-02 fires, rerun market + predict — the source tape moved after this chain started.

View: the deployed UI (Render) reads the published bundle through the Vercel API within
~30 s — see `DEPLOY.md`. Locally: `scripts/serve_top150_console.sh` (:8790, files) or
`app/backend && npm start` (Mongo via `.env`).

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
  `RUNPOD_GPU_TYPES='["NVIDIA GeForce RTX 4090","NVIDIA RTX A5000","NVIDIA A40","NVIDIA RTX A4500","NVIDIA RTX A6000","NVIDIA GeForce RTX 3090","NVIDIA L4","NVIDIA RTX 4000 Ada Generation","NVIDIA A30"]' scripts/launch_top150.sh stage2`
- **Interpreting results**: stage1 KILL is NOT diagnostic — the book only emerges at
  stage3. Known baseline (2026-09-01 full run): stage3 ungated 9.6% CAGR / SR 0.59 /
  MDD −45%; last-3y 13.3%/0.64; `lgbm_h5` degenerates on 150 names (valid RIC 0.0000
  every fold) and M10-03 admits only h20+h60.

Then publish with the stage artifacts re-pulled:

```sh
FULL_MIRROR=1 .claude/skills/top150-pipeline/scripts/mirror_top150.sh
```

The refreshed `derived/top150/` artifacts are committed on this branch (that is the
record — check `git status` after the mirror and commit them with the bundle).

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
