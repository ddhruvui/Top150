# Run prompt — nightly pipeline

Paste one of these into Claude Code from the repo root. The `daily-pipeline` skill
(`.claude/skills/daily-pipeline/`) carries the ordering rules and verification steps, so the
prompt itself can stay short — it does not need to re-explain the pipeline.

**On this branch (`top150`/`top200`)** the same prompt does more: after the prod chain and
mirror, the run continues into the top-150 daily loop — `launch_top150.sh market` →
`predict` on the k4cli3aj48 calc volume, then `mirror_top150.sh` → `reports/top150` — via
the `top150-pipeline` skill (`.claude/skills/top150-pipeline/`). No wording change needed.

## The one to use

> Run launch all and keep monitoring. Make sure the downloads from every service complete,
> verify them, and then run the remaining steps. While the pods run, watch for errors and for
> pods stuck in a bad state. Do the needful.

Best fired **after 21:00 UTC** (17:00 ET). EODHD publishes the bulk day-file around 23:30 UTC,
so later in the evening is safer, not worse. (The fetcher re-pulls the trailing few sessions
each night, so an early or light pull self-heals the next night — but the book prices against
tonight's pull, so launch late anyway.) Measured 2026-09-03: the day-file keeps FILLING for
hours after it first appears — a 01:30 UTC pull froze 35k rows with real S&P names missing
(AAPL included) and the row-floor guard did not catch it; the complete same-night file
(~44k rows, ~12% light on fund-NAV series only) wasn't there until ~02:50 UTC. If the pull
looks light, the `eodhd-bulk-publishes-late` memory has the surgical re-pull recipe.

## Variants

**Data already fetched, just redo the modelling:**

> The vendor fetch is already done for tonight. Verify the manifests are fresh, then run
> market and predict and rebuild the reports bundle.

**Resume after a failure:**

> The pipeline failed partway last night. Work out which stage broke, fix it, and carry the
> run through to the reports bundle. Tell me what actually failed and why.

**Just check on it:**

> Check the pipeline: what pods are running, how far along are they, and is anything stuck?

**Force a full model refit** (normally automatic every 21 labelled sessions):

> Run the daily pipeline, but force a from-scratch refit rather than a warm update.

## What "done" looks like

Ask for these back, and treat anything missing as not-done:

- Per-vendor `jobs / ok / fail` — **fail must be 0** across all six trees
- The session that just closed present in `data/eod_bulk/US/`
- `validate exit=0` **and** `build_m1 exit=0`, with an `m1/_manifest.json` from this run
- `market job=0`, `predict job=0`
- **G-02**: `suggestions.json`'s `as_of_close` equals the newest day-file
- Results pulled **down to this machine** — `derived/suggestions.json` and
  `reports/suggestions_latest.md` present and dated today
- `reports/latest/` rebuilt (that bundle is the whole contract with the UI), plus the book size

On this branch, additionally:

- top150 `market job=0` and `predict job=0` (logs on **k4cli3aj48** — `podlog150`, not `podlog`)
- top150 **G-02**: `derived/top150/predict/suggestions.json` `as_of_close` equals the newest
  prod day-file, and `reports/top150/` rebuilt with the top150 book size

The pods write to the network volume, not to your disk — until the mirror step runs there is
nothing local to look at and the UI still shows the previous run. If you only want that last
step, say so rather than re-running the pipeline:

> Everything already ran on the pods. Just pull the results down and rebuild the reports bundle.

Then view it with `cd app/backend && npm start` (http://localhost:8787).

A pod exiting is not evidence a stage succeeded — a stage can be OOM-killed (`exit=-9`) while
its pod still self-terminates normally and leaves yesterday's output in place. Ask for exit
codes, not "it finished".

## Not included

`stage1`, `stage2`, `stage3` are the research/backtest stages and are deliberately outside the
daily loop; they are rerun on code or config changes, or on the monthly cadence to refresh the
G-11 gate. The dashboard's verdict, equity curve and trade counts come from their existing
reports, so those numbers not moving after a daily run is expected.

Ask for them explicitly if you want them — the `monthly-pipeline` skill
(`.claude/skills/monthly-pipeline/`) carries that runbook:

> Run the monthly stage refresh.

or, for a partial rerun:

> Also rerun stage1 and stage3 to refresh the gate verdict.

On this branch, the top-150 stage refresh runs on the **quarterly** cadence instead, via the
`top150-pipeline` skill (stage1 → stage2 GPU → stage3 on k4cli3aj48, then
`FULL_MIRROR=1 mirror_top150.sh` and commit the refreshed `derived/top150` artifacts):

> Run the top150 quarterly refresh.
