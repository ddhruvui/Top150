# EOD Swing & Position Trading System

Implementation of [stock_prediction_implementation_blueprint_v1_0_1.md](stock_prediction_implementation_blueprint_v1_0_1.md)
(verified by [blueprint_verification_report_v1.md](blueprint_verification_report_v1.md)).
**This repo computes; it does not ingest.** A **separate system** downloads all vendor
data onto the volume `crimtr8kbf`, whose root (`data/`, `m1/`, `m1x/`, …) this repo reads
**strictly read-only**. Everything computed here lands under `results/Core105/` on that
same volume and nowhere else (the old calc volume `k4cli3aj48` is retired). See
[dailyuse.md](dailyuse.md) and the `core105-pipeline` skill;
`scripts/test_volume_guards.sh` proves the write boundary.

## Layout (blueprint §8)

```
configs/system.yaml     # §3 registry — SHA-256 = config_hash on every artifact (G-10)
src/
  data/        M2  m1.py (M1 readers), panel.py (Q-002 adj panel), universe.py (Q-003),
               health.py (Q-004), pit.py (M2-03), build_market.py (whole-market m1x),
               market.py, index_prices.py
  primitives/  M3  returns, ewma (sigma32), rolling (Q-015 cache), fwd (THE +1 lag),
               csnorm (Q-017), monthly (mom_12_1), index (Q-019)
  features/    M4  technical (F1-F6), fundamental (F7 PIT), events (F8), sentiment (F9),
               pipeline (winsorize -> CS-rank -> manifest)
  labels/      M5  heads.py (y5/y20/y60), barriers.py (C-06 — THE triple-barrier engine)
  models/      M6 lgbm.py | M7 gru.py | M8 cnn/{render,net}.py (JKX exact)
  ensemble/    M10 rank.py          meta/    M11 gate.py
  classical/   M12 momentum.py      regime/  M13 overlay.py
  portfolio/   M14 construct.py
  backtest/    M15 engine.py (fast path), engines/barriers_event.py (event confirmation),
               costs.py (C-08), compliance.py (PDT/tax)
  validation/  M16 splits.py (C-07 purge+embargo, CPCV 6/2), metrics.py, dsr.py,
               baselines.py (G-08), gates.py (G-11)
  hpo/         M17 determinism.py, ledger.py (DSR N), search.py (Optuna <=100)
  live/        M18 orders.py (order FILES + nightly trailing-stop re-peg; submission stays manual)
  pipeline/    stage1.py, stage2.py, stage3.py, predict.py, common.py
tests/         §9 T-01..T-15 (pytest; also runs on the pod via JOB=test)
ledger/trials.parquet   # every evaluated config -> DSR's N (G-09)
```

## RunPod jobs

Every job goes through `launch_core105.sh`, which wires `results/Core105` for output and
the rest of the volume for read-only input. There is no fetch stage and no `daily.sh`.

```sh
# gate first: has the separate download system finished for this session?
.claude/skills/core105-pipeline/scripts/verify_source.py

scripts/launch_core105.sh test       # T-suite on a CPU pod (validates pod env)
scripts/launch_core105.sh market     # -> m1x105: the FIXED 105-name universe from
                                    # configs/system_core105.yaml. Resumable.
scripts/launch_core105.sh stage1     # features -> LGBM heads (purged WF) -> ensemble
                                    # -> portfolio -> backtest -> G-11 gates
scripts/launch_core105.sh stage2     # + GRU + JKX CNN + FinBERT (GPU pod)
scripts/launch_core105.sh stage3     # meta gate + barrier book + CPCV
scripts/launch_core105.sh predict    # latest-date scores -> target book -> suggestions.
                                    # Continual: warm-updates champions stored under
                                    # results/Core105; full refit auto every 21 sessions or
                                    # on config/feature change; REFIT=full forces it.

# the predict pod then publishes on its own: G-02 against the source tape -> bundle
# -> MongoDB -> deployed UI (tools/pod_publish.sh); the stage3 pod publishes the
# research sections the same way (book untouched). Optional laptop path for the git
# record (re-publishes the same content):
.claude/skills/core105-pipeline/scripts/mirror_core105.sh
```

The research console (`app/`) is deployed — API on Vercel, UI on Render — and reads
the bundle from MongoDB; see [DEPLOY.md](DEPLOY.md). `scripts/push_repos.sh` pushes
this repo and the two deploy repos together.

`USE_MARKET=0` restricts to the 506-name M1 layer (pipeline validation only —
survivorship-biased, never for go/no-go). `KEEP_POD=1` keeps the pod for
inspection. EU-RO-1 CPU capacity is patchy: `RUNPOD_VCPU=2` almost always
places; jobs are engineered to fit 4 GB.

Local (mirror or synthetic): `python -m src.pipeline.stage1 --m1 <m1> --eod <data> --out <dir>`;
`tests/make_synth_m1.py` builds a synthetic M1 layer for rehearsal.

## Verification status

- T-01..T-15 pass locally and on-pod (incl. T-13 golden images, CPCV 15/5/5 exact).
- DSR formula replicates the audit's calibration (SR 1.5/5y/100 trials -> ~0.8;
  best-of-100 null -> ~0.2 "correctly unimpressed").
- Planted-signal synthetic -> G-11 sanity ceiling fires (LEAKAGE-AUDIT verdict);
  zero-signal synthetic -> no trades, KILL on NaN metrics. Both by design.
- Engine cross-checks: fast path == closed-form w·oo at zero cost (1e-10);
  cost drag == the engine's own cost ledger; event engine (barrier exits) is the
  §J second-engine confirmation.

**Exit rule (2026-09-08):** M5.2 triple barrier plus a trailing stop
(`barrier.trail_m: 1.0` — the GTC stop is re-pegged nightly to the high since
fill minus 1σ√h, never below the fixed stop; `src/live/orders.py::trailing_stops`).
Adopted from rounds H-J, see `reports/exp_short/ANALYSIS.md`.

**Short sleeve (2026-09-17, blueprint `port.selection` [MAY]):** the book is long
top-decile plus **short bottom-10** (`port.short_selection: bottom_n`, `short_n: 10`),
the 1.0 cash cap split `long_gross_cap: 0.5` / `short_gross_cap: 0.5` — long + short
live gross never exceeds NAV, so no cash is borrowed; the margin account only carries
the share loan. A short is a sale of borrowed shares (SELL MOO to open, BUY to cover)
through the ONE barrier engine: stop above the fill, trail ratcheting down off the low
since fill, profit-take below, vertical = BUY MOO cover; the per-name iBorrowDesk fee
accrues daily and names above `short_max_borrow_bps_yr` are skipped (§I.4). Code path:
`select_short` -> `run_long_short` (two sleeves of `run_event_backtest`, each under its
cap) -> `live_book(side=-1)`; the ticket adds `shorts_or_increases` / `short_holds` /
`covers_or_exits`; `orders.py` emits the mirrored stop/limit/cover orders. Every path is
bit-identical to the long-only book when the `short_*` keys are absent
(`tests/test_short_side.py`). **Not yet run on the pods** — no backtest number exists
for the short leg; the M17 harness carries `short_n` / `short_decile` / `short_cap`
levers for that.

**Not enabled (spec-sanctioned):** M9 optional models (GKX NN, Sharpe-loss net,
101 Alphas) sit behind config flags, off by default. RL-as-primary, foundation
time-series models, and plain Transformers are excluded per M9.5 [MUST NOT].

Research tooling for the operator of this repo — not financial advice (CAV).
