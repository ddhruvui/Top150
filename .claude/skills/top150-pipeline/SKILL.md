---
name: top150-pipeline
description: Run and monitor the TOP-150 experiment pipeline — the daily loop (market → predict → reports/top150 bundle) and the quarterly research refresh (stage1 → stage2 GPU → stage3 → FULL_MIRROR) — on the k4cli3aj48 calc volume, reading crimtr8kbf strictly read-only. Use this whenever the user asks to run the top150 daily or quarterly steps, refresh the top150 book/suggestions/reports, rerun top150 stage1/2/3, or check on top150 pods — and for anything on the top150/top200 branches that would otherwise reach for launch_predict.sh or the daily-pipeline skill directly. The volume contract and the watch_jobs.sh hazard are not visible from the scripts themselves.
---

# Top-150 pipeline: daily and quarterly

The top-150 experiment runs the adopted aggressive cash config on a point-in-time
top-150 dollar-volume stock universe. Same prediction stack, different wiring:

- **`k4cli3aj48`** — calc volume, mounted by pods at `/workspace`. Holds ONLY computed
  artifacts: `m1x150/`, `derived/top150/*`, `models/`, `ledger/`, `_pod_logs/`.
- **`crimtr8kbf`** — prod data volume, **read-only source**. Never mounted, never
  written; pods pull inputs via S3 GETs into container-local `/scratch`
  (the `SRC_VOLUME_ID` prefetch block in `pod_bootstrap_predict.sh`).

`scripts/launch_top150.sh <market|stage1|stage2|stage3|predict>` sets all of this
(volume override, `UNIVERSE_SIZE=150`, `MARKET_DIR=/workspace/m1x150`,
`SYSTEM_CONFIG=configs/system_top150.yaml`, `OUT_DIR=/workspace/derived/top150/<job>`)
and hands off to `launch_predict.sh`. It refuses to run if calc==source.

Bundled helpers in `.claude/skills/top150-pipeline/scripts/` (call by full path;
`SK150=.claude/skills/top150-pipeline/scripts`):

| script | what it does |
|---|---|
| `vol150` | `aws s3` against the CALC volume — `vol150 ls derived/top150/predict/` |
| `podlog150 <pat> [n]` | newest matching `_pod_logs/` entry **on k4cli3aj48** — top150 pod logs are here, the daily-pipeline `podlog` cannot see them |
| `mirror_top150.sh` | pull book (+stage artifacts with `FULL_MIRROR=1`), enforce G-02 vs the PROD tape, rebuild `reports/top150` |

For anything prod-side (pods list, prod volume reads, watchdog), reuse the
**daily-pipeline** skill's helpers — `pods` and `watch_pods.py` are account-wide and
see top150 pods too.

## Hard rules (each one has burned a run)

1. **NEVER run `scripts/watch_jobs.sh` for this experiment.** It watches the prod
   bucket and its auto-relaunch re-runs the job with PROD wiring — it would mount and
   write crimtr8kbf. Use daily-pipeline's `watch_pods.py` (report-only) instead.
2. **Never write to crimtr8kbf** from this pipeline, and never mount it
   (`launch_top150.sh` enforces both; don't work around it with launch_predict.sh
   directly — that is exactly the mistake the wrapper exists to prevent).
3. **Branch check first**: `git branch --show-current` must say `top150` (or `top200`).
   The backend's branch-aware bundle selection (`app/backend/src/reports.js`) serves
   `reports/top150` only on those branches; on `main` you'd rebuild the wrong bundle.
4. A launched pod with **no bootstrap log on k4cli3aj48 within ~5 min** is on a broken
   EU-RO-1 host (struck twice for the market job on 2026-09-01): it bills forever while
   RUNNING and never starts. Check `$SK150/vol150 ls _pod_logs/ | tail`, then DELETE the
   pod and relaunch. `launch_predict.sh` does not verify startup for you.
5. If another session's prod watchdog is running, it leaves `predict-*` pods it didn't
   launch alone (agreed 2026-09-01) — but don't run two top150 chains at once.

## Daily loop

**Prerequisite — the PROD daily pipeline must be done through its `market` job for the
session.** The top150 `market` job does not parse eod_bulk itself: the prefetch pulls
prod's already-parsed `m1x/market_prices` parts + `m1/entities.parquet` and sets
`SKIP_BULK=1`; `predict` pulls the whole `m1/` tree. Stale prod ⇒ stale top150, and a
partial eod_bulk day-file on prod (see the `eodhd-bulk-publishes-late` memory) poisons
this book too. Verify first:

```sh
python3 .claude/skills/daily-pipeline/scripts/verify_fetch.py   # all FRESH, fail=0
.claude/skills/daily-pipeline/scripts/podlog predict-market 5   # prod market job=0
```

Then, in order (each: launch → confirm bootstrap log → wait → verify exit):

```sh
scripts/launch_top150.sh market     # membership@150 + workset -> /workspace/m1x150
scripts/launch_top150.sh predict    # book -> /workspace/derived/top150/predict
```

After each launch confirm `$SK150/vol150 ls _pod_logs/ | tail -2` shows a fresh
`predict-<job>-<podid>.log` (rule 4 if not). After each pod self-terminates, require
`job=0` in `$SK150/podlog150 predict-<job>`. The predict job's champion store and
trials ledger live on k4cli3aj48 (`/workspace/models`, `/workspace/ledger`) — fresh
history, so a full refit instead of a warm update is normal early on, and its DSR/N is
NOT comparable to prod's ledger.

Finish by publishing:

```sh
.claude/skills/top150-pipeline/scripts/mirror_top150.sh
```

It pulls `suggestions.json`, enforces **G-02 for this book** (`as_of_close` must equal
the newest `data/eod_bulk/US/` day-file **on crimtr8kbf**), stages a flat src dir, and
rebuilds `reports/top150` with the top150 config hash. If G-02 fires, rerun
market + predict here — the prod tape moved after this chain started.

View: `scripts/serve_top150_console.sh` (:8790, prod console on :8787 untouched), or
`app/backend && npm start` on this branch (branch-aware bundle pick, restart after
checkout).

## Quarterly research refresh (stage1 → stage2 → stage3)

Run after config/code changes or on the quarterly cadence — this is the top150
equivalent of the monthly-pipeline skill, same stage semantics:

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
- **Interpreting results**: stage1 KILL is NOT diagnostic — prod stage1/stage2 are
  also KILL under the adopted config; the book only emerges at stage3. Known baseline
  (2026-09-01 full run): stage3 ungated 9.6% CAGR / SR 0.59 / MDD −45%; last-3y
  13.3%/0.64 vs prod 29.9%/1.45; lgbm_h5 degenerates on 150 names (valid RIC 0.0000
  every fold) and M10-03 admits only h20+h60.

Then publish with the stage artifacts re-pulled:

```sh
FULL_MIRROR=1 .claude/skills/top150-pipeline/scripts/mirror_top150.sh
```

The refreshed `derived/top150/` artifacts are committed on this branch (that is the
experiment's record — check `git status` after the mirror and commit them with the
bundle).

## Monitoring

Same idioms as daily-pipeline: start `watch_pods.py` under a Monitor (wrapped in
`caffeinate -dims`), read logs with `podlog150` before acting on a STALL, and never
treat "pod gone" as success — only `job=0` in the log is success. Rough runtimes from
the 2026-09-01 run: market ~minutes, predict ~minutes (longer on full-refit days),
stage1 hours, stage2 the long pole (GPU), stage3 ~1-2 h.

## Reporting back

Per job: pod id, `job=0` (or the failing line), and for the daily loop the G-02 result
plus book size (`suggestions.json` n / as_of). For the quarterly loop: the stage3
verdict line, CPCV median, and whether the bundle + committed artifacts changed.
