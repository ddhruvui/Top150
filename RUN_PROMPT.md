# Run prompt — the daily loop

Paste one of these into Claude Code from the repo root. The `top150-pipeline` skill
(`.claude/skills/top150-pipeline/`) carries the ordering rules, the volume contract and the
verification steps, so the prompt itself can stay short.

**This repo does not download anything.** A separate system fills the source volume
`crimtr8kbf`; this repo reads it strictly read-only and computes onto `k4cli3aj48`. So the
run starts by *checking* the source is complete, not by fetching it.

## The one to use

> Run the daily loop and keep monitoring. Verify the source data is complete first, then run
> market and predict and publish the bundle. While the pods run, watch for errors and for pods
> stuck in a bad state. Do the needful.

Best fired once the upstream download system has finished for the session. EODHD publishes the
bulk day-file around 23:30 UTC and it keeps **filling for hours** afterwards (measured
2026-09-03: a 01:30 UTC snapshot froze 35k rows with real S&P names missing, AAPL included; the
complete ~44k-row file wasn't there until ~02:50 UTC). `verify_source.py` checks manifests, not
row counts, so a light day-file can still pass — if the resulting book looks wrong, suspect this
first.

## Variants

**Just check whether the source is ready:**

> Is the source tape complete for tonight? Don't launch anything.

**Resume after a failure:**

> The loop failed partway last night. Work out which stage broke, fix it, and carry the run
> through to the reports bundle. Tell me what actually failed and why.

**Just check on it:**

> Check the pipeline: what pods are running, how far along are they, and is anything stuck?

**Force a full model refit** (normally automatic every 21 labelled sessions):

> Run the daily loop, but force a from-scratch refit rather than a warm update.

**Quarterly research refresh:**

> Run the top150 quarterly refresh.

## What "done" looks like

Ask for these back, and treat anything missing as not-done:

- `verify_source.py` — every tree **FRESH**, `fail=0`
- `market job=0` and `predict job=0` — logs on the **calc volume** (`podlog150`)
- **G-02**: `suggestions.json`'s `as_of_close` equals the newest source day-file
- `publish=0` in the predict pod log — the pod built the bundle and published it to MongoDB;
  the deployed UI (see `DEPLOY.md`) shows it within about 30 seconds. `publish=3` means G-02
  failed on the pod (stale close): rerun market + predict.

Nothing has to come down to this machine. `mirror_top150.sh` is optional: it pulls the
artifacts, rebuilds `reports/top150` for the git record and re-publishes the same content.
Locally: `scripts/serve_top150_console.sh` (:8790).

A pod exiting is not evidence a stage succeeded — a stage can be OOM-killed (`exit=-9`) while
its pod still self-terminates normally and leaves yesterday's output in place. Ask for exit
codes, not "it finished".

## Not included

**Vendor downloads.** If the source tape is stale, incomplete, or a vendor tree is failing,
that is the separate download system's job. Report it; do not add a fetch here. There is no
`data_acquisition/`, no `daily.sh` and no `watch_jobs.sh` in this repo any more, and the volume
guards will refuse anything that tries to write the source.

`stage1`, `stage2`, `stage3` are the research/backtest stages and sit outside the daily loop;
they are rerun on code or config changes, or on the quarterly cadence to refresh the G-11 gate.
The dashboard's verdict, equity curve and trade counts come from their existing reports, so
those numbers not moving after a daily run is expected. Ask for them explicitly:

> Run the top150 quarterly refresh.
