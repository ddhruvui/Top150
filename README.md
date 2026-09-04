# EOD Swing & Position Trading System

Implementation of [stock_prediction_implementation_blueprint_v1_0_1.md](stock_prediction_implementation_blueprint_v1_0_1.md)
(verified by [blueprint_verification_report_v1.md](blueprint_verification_report_v1.md)).
**This repo computes; it does not ingest.** A **separate system** downloads all vendor
data onto the source volume `crimtr8kbf`, which this repo reads **strictly read-only** —
never mounted, never written. Everything computed here lands on the calc volume
`k4cli3aj48`. See [dailyuse.md](dailyuse.md) and the `top150-pipeline` skill.

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
  live/        M18 orders.py (order FILES; submission stays manual)
  pipeline/    stage1.py, stage2.py, stage3.py, predict.py, common.py
tests/         §9 T-01..T-15 (pytest; also runs on the pod via JOB=test)
ledger/trials.parquet   # every evaluated config -> DSR's N (G-09)
```

## RunPod jobs

Every job goes through `launch_top150.sh`, which wires the calc volume for output and
the source volume for read-only input. There is no fetch stage and no `daily.sh`.

```sh
# gate first: has the separate download system finished for this session?
.claude/skills/top150-pipeline/scripts/verify_source.py

scripts/launch_top150.sh test       # T-suite on a CPU pod (validates pod env)
scripts/launch_top150.sh market     # -> m1x150: point-in-time top-150 dollar-volume
                                    # universe, survivorship-free (G-05). Resumable.
scripts/launch_top150.sh stage1     # features -> LGBM heads (purged WF) -> ensemble
                                    # -> portfolio -> backtest -> G-11 gates
scripts/launch_top150.sh stage2     # + GRU + JKX CNN + FinBERT (GPU pod)
scripts/launch_top150.sh stage3     # meta gate + barrier book + CPCV
scripts/launch_top150.sh predict    # latest-date scores -> target book -> suggestions.
                                    # Continual: warm-updates champions stored on the
                                    # calc volume; full refit auto every 21 sessions or
                                    # on config/feature change; REFIT=full forces it.

# publish: G-02 against the source tape, rebuild reports/top150, push it to MongoDB
.claude/skills/top150-pipeline/scripts/mirror_top150.sh
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

**Not enabled (spec-sanctioned):** M9 optional models (GKX NN, Sharpe-loss net,
101 Alphas) sit behind config flags, off by default. RL-as-primary, foundation
time-series models, and plain Transformers are excluded per M9.5 [MUST NOT].

Research tooling for the operator of this repo — not financial advice (CAV).
