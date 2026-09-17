# Daily use — prediction stack (blueprint v1.0.1 implementation)

> **This repo computes; it does not ingest.** There is no vendor-download code here.
> A **separate system** owns every fetch that fills the volume `crimtr8kbf`, and this
> repo reads its root (`data/`, `m1/`, `m1x/`, …) **strictly read-only**. Everything
> computed here lands under `results/Core105/` on that same volume and nowhere else
> (the old calc volume `k4cli3aj48` is retired; same relative layout, one prefix down).
> The contract is enforced in `scripts/_common.sh` and re-asserted in
> `scripts/launch_predict.sh` and `scripts/pod_bootstrap_predict.sh`;
> `scripts/test_volume_guards.sh` proves it.
>
> Before computing, gate on the source being complete for the session:
> `.claude/skills/core105-pipeline/scripts/verify_source.py` (exit 0 = every vendor
> tree fresh, zero hard failures). If it fails, that is the other system's problem
> to fix — report it rather than trying to fetch anything here.

The modelling/backtest/prediction system lives at repo root (`src/`, `configs/system.yaml`,
`tests/` — see [README.md](README.md)). **All processing runs on RunPod**: pods mount
`crimtr8kbf`, write only under `/workspace/results/Core105`, and read their inputs
read-only into `/scratch` over S3. Local execution is for
unit tests and synthetic rehearsals only.

```sh
# THE daily loop is now two launches plus a mirror — there is no fetch stage here.
scripts/launch_core105.sh market     # fixed membership + workset -> results/Core105/m1x105
scripts/launch_core105.sh predict    # book -> results/Core105/derived/core105/predict, then the
                                    # POD publishes: G-02 -> bundle -> MongoDB -> deployed UI
.claude/skills/core105-pipeline/scripts/mirror_core105.sh   # optional: git record + re-publish

scripts/launch_core105.sh test      # T-01..T-15 suite on a CPU pod (validates pod env)
scripts/launch_core105.sh market    # eod_bulk -> m1x105 panel + the fixed 105-name
                                    #   universe (configs/system_core105.yaml); resumable
scripts/launch_core105.sh stage1    # features -> LGBM heads (purged WF) -> book -> gates
scripts/launch_core105.sh stage2    # + GRU + JKX CNN + FinBERT (GPU pod)
scripts/launch_core105.sh stage3    # meta gate + barrier-exit event book + CPCV(6,2)
                                    #   (reads SCORES_DIR, default results/Core105/derived/core105/stage2)
scripts/launch_core105.sh predict   # latest-close scores -> target book -> suggestions
                                    #   (continual: warm-updates stored champions daily,
                                    #   full refit auto every 21 sessions — see below)

# Report-only watchdog (one line per state change). It deliberately does NOT
# auto-relaunch: the old watch_jobs.sh did, with prod wiring, and that is exactly
# how an unattended run ended up writing the source tape.
.claude/skills/core105-pipeline/scripts/watch_pods.py
```

## Incremental daily learning (the Monday-morning answer)

Nothing retrains from scratch daily. The `predict` job is **continual**: LGBM champions
persist on the volume under `/workspace/results/Core105/models/` (`MODEL_DIR`), and each daily run

1. **decides the mode** — `update` if every head has a champion trained under the current
   `config_hash` and the last FULL fit is < `continual.full_refit_sessions` (21 ≈ monthly,
   = `val.retrain_cadence`) worth of *newly labeled* sessions old; else `full`;
2. in `update` mode loads only a `panel_tail_years` (5y) slice of the panel — year-parts
   before the tail are never even read — and **warm-continues** each champion with
   LightGBM `init_model` on the newest labeled year (purged against the valid year,
   `update_learning_rate` 0.02, ≤ `update_boost_rounds` extra trees);
3. **champion vs challenger**: both are scored on the SAME purged valid year (mean daily
   Rank IC); the challenger is adopted only if it wins. Learning accrues when the new
   data teaches something; a noise-day challenger is rejected and the champion stands;
4. logs every fit — adopted or rejected — to the G-09 trials ledger (DSR's N stays honest),
   and stamps the decision into `suggestions.json` under `"training"`.

`REFIT=full scripts/launch_core105.sh predict` forces a from-scratch fit (also automatic
after any `configs/system.yaml` change, feature-set change, or on the 21-session cadence).

**The loop is: verify source → market → predict (which publishes itself).** The mirror is
optional — it refreshes the local `reports/core105` git record. There is no one-command
`daily.sh` any more, and deliberately so — it began by launching the vendor fetch and
then ran market/predict with wiring that mounted and wrote the source tape. Each step
is now explicit, and each is gated on the previous one reporting `job=0` (a pod exiting
proves nothing). The `core105-pipeline` skill carries the ordering rules and the
"looks finished but silently half-built" failure modes.

Stage 1/2/3 are the research/backtest reports — they only need re-running when code or
config changes, or on the quarterly cadence to refresh the G-11 gate verdict; they are
deliberately not part of the daily loop. The **stage3 pod publishes** the refreshed
research sections itself (gates, equity, ledger — the book is left untouched, see the
skill); `FULL_MIRROR=1 mirror_core105.sh` is the optional laptop path that re-pulls the
parquets for the git record.

- Pods self-terminate with a confirmed DELETE; a restart marker prevents billing loops.
  `KEEP_POD=1` keeps a pod alive for inspection; `RUNPOD_VCPU=8` (16 GB) is required for
  stage1/stage3/predict (the 4 GB default OOMs); stage2 needs the GPU flavor (automatic).
- Outputs land under `results/Core105/derived/core105/<job>/` (reports, scores, target
  weights, suggestions). Pull with the results helper (bare paths are relative to
  `results/Core105`):
  `.claude/skills/core105-pipeline/scripts/vol105 cp derived/core105/stage3/ ./derived_stage3/ --recursive`
- `derived_*/` downloads are disposable and gitignored; keep only
  `artifacts/reports/*.json|md` (small, reviewable) and `ledger/trials.parquet`
  (G-09 append-only trials ledger feeding the Deflated Sharpe N).
- Ordering: `market` must exist before stage1/predict (`USE_MARKET=1` default);
  stage3 needs a prior stage1 or stage2 scores directory; predict is independent of
  stage3 and can run daily after `launch.sh all` + `post`.
- Tape hygiene for the whole-market panel (bar sanity, vintage seams, V-spikes,
  level flips, tape breaks) is applied inside `build_panel()` — see
  `src/data/panel.py` and the memory note `eod-bulk-tape-hygiene`.

## Research console (reports + paper trading)

Final reports live in **`reports/`** — `suggestions_core105.md` is the human-readable
book, `reports/core105/*.json` is the machine bundle the app serves (built from the
stage artifacts mirrored under `derived/core105/`), and `reports/exp_short/` is the
experiment record (ranked variant tables + ANALYSIS.md).

```sh
# refresh the bundle after a pipeline run (pods write results/Core105; this only reads)
# — ends by publishing reports/core105 to MongoDB, which is what the deployed UI shows
.claude/skills/core105-pipeline/scripts/mirror_core105.sh          # daily book + bundle
FULL_MIRROR=1 .claude/skills/core105-pipeline/scripts/mirror_core105.sh   # after a stage rerun
python3 tools/publish_mongo.py                  # publish only (bundle already built)

# the deployed console: API on Vercel (Top150BE repo), UI on Render (Top150FE repo) — DEPLOY.md
# locally:
cd app/backend && npm install && npm start      # http://localhost:8787 (reads Mongo via .env)
cd app/frontend && npm run dev                  # hot-reload UI on :5173, proxies /api
cd app/backend && npm test                      # paper-book regression suite
```

Five pages: **Today** (the trade ticket — next-session orders, diffed against
what you hold, so new buys are distinguished from existing positions; it is the
landing page), **Dashboard** (G-11 verdict, gate table, equity curve, member Rank ICs,
CPCV spread, baselines), **Suggestions** (target book + barrier levels, push to
paper), **Backtest** (what was suggested vs what happened across 376k barrier
trades), **Paper trading** (BP15: record fills to measure open-print slippage,
PDT budget, kill switch, decay monitor). See [app/README.md](app/README.md).
