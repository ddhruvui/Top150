# Short-horizon experiment (branch `exp-short-horizon`)

Question: can the top-150 book hold for **a week or less** and keep (or beat) its
profit, and why did the published backtest stop trading in March 2026?

Everything here is research tooling evaluated under the repo's own gates — not
financial advice. All numbers are net of the stated per-leg cost, walk-forward,
on the scored window only (the harness convention; `stage3_report` headline
Sharpe is diluted by pre-2007 flat days, so the anchor here reads 0.71 where the
published bundle says 0.59 for the same book).

## 1. The backtest stopped in January/March 2026 — root cause and fix

`walk_forward()` only emitted **full** 252-session test blocks, so the tail of the
panel after the last full year (2026-01-22 onward) was never scored. The last
entries were 2026-01-21 and their 40-session verticals landed in late March —
hence "no trades after March 26".

Fix (`src/validation/splits.py`, `val.partial_last_fold_min_sessions: 21` in
`configs/system_top150.yaml`): one extra final fold whose test block runs to the
last session, purged and embargoed like every other fold. Default off = the old
folds bit-for-bit (T-02/T-03 still pass on the partial fold).

Evidence, stage1 rerun 2026-09-07: **20 folds instead of 19**, scores from
2007-01-10 to **2026-09-04** (the last session on the source tape). stage2/stage3
reruns with the same fix are in `derived/exp_short/` on the calc volume.

## 2. Round H — 27 variants on the cached 2026-09-01 stage-2 scores

Full table: [roundH_cached/summary.md](roundH_cached/summary.md). Anchor =
the adopted book (h40, top-5, vt 20%, all seven members, 15 bps).

| what changed | SR | CAGR | MDD | hold (sessions) |
|---|---|---|---|---|
| anchor: adopted book, 7 members | 0.71 | 14.0% | -45.0% | 34.7 |
| drop CNN (below the 0.02 admission floor) | 0.76 | 16.0% | -43.5% | 34.7 |
| **admission floor: h20+h60 members only** | **0.81** | **17.3%** | -45.0% | 34.7 |
| floor, 5 bps/leg | 0.86 | 18.6% | -44.6% | 34.7 |
| floor + trailing stop 1.0σ√h | 0.86 | 17.1% | -40.0% | 27.9 |
| floor + dead-money exit at 20 sessions | 0.84 | 17.3% | -40.9% | 27.0 |
| floor + dead-money exit at 10 sessions | 0.82 | 16.6% | **-37.8%** | 23.1 |
| floor, h20 vertical | 0.80 | 15.1% | -37.5% | 17.5 |
| **floor, h10, 5 bps** | **0.84** | 15.0% | **-31.5%** | **8.8** |
| floor, h10, 10 bps | 0.76 | 13.3% | -32.4% | 8.8 |
| floor, h10, 15 bps | 0.67 | 11.5% | -33.3% | 8.8 |
| **floor, h7, 5 bps** | **0.83** | 14.7% | **-28.3%** | **6.1** |
| floor, h7, 10 bps | 0.72 | 12.4% | -29.9% | 6.1 |
| h20 members, h5, 5 bps | 0.71 | 12.3% | -35.2% | 4.4 |
| h20 members, h5, 10 bps | 0.57 | 9.3% | -37.0% | 4.4 |

Findings, in order of size:

1. **Member admission is the free win.** `stage3` loads every scores file and
   never applies the M10-03 floor, so `lgbm_h5` (Rank IC −0.02 on 150 names,
   valid RIC 0.0000 on 18 of 20 folds) and the CNN (0.004) vote on the top-5.
   Dropping them: +0.10 Sharpe, +3.3pp CAGR, same hold. This applies to the
   production book regardless of horizon.
2. **Cost decides whether a one-week hold works.** At h7 the same book goes
   0.83 → 0.72 → ~0.6 Sharpe at 5 → 10 → 15 bps/leg. At 15 bps nothing under
   h20 beats the anchor (which is what rounds A-G found on the 1000-name
   universe). At 5 bps — defensible for market-on-open fills in the 150 most
   liquid US names, but **an assumption until the console's slippage log says
   so** — h7 and h10 match the 40-session book on Sharpe with drawdowns 13-17pp
   shallower. CAGR is lower (14.7-15.0% vs 17.3%) mainly because…
3. **…short cycles leave capital idle.** Realized gross is 0.76x at h7/h10 vs
   0.92x at h40: a third of positions leave early through a barrier and the
   exact cash cap only ever scales the next tranche *down*. Round I adds
   `fill_max` (scale the entering tranche up, to at most 1.5-2x nominal, never
   above the 1.0x cap) to re-deploy that capital.
4. **Trailing stop 1.0σ√h and the dead-money exit shorten the 40-session book
   by 1-2 weeks at equal Sharpe and better drawdown.** A tighter trail (0.7)
   loses: it stops out too many working trades (win rate 43%). Neither helps at
   h10, where the fixed barrier is already narrow.
5. **What hurt:** the trend filter (close above 20/60-day averages) starves the
   book — it removes ~65% of entries and gross falls to 0.6x; conviction
   tilt is neutral; the 5-day heads add nothing even at h5 (`fast4` 0.67 vs
   0.71 with h20 members alone); every combo of trend + trail + tilt is worse
   than its parts.
6. **Earnings skip** is neutral at h40 (as before) and is kept on for h ≤ 10,
   where a single gap is the whole trade.

## 2b. Round I — 26 variants on the h5/h7/h10 winners (cached scores, 5 bps unless noted)

Full table: [roundI_cached/summary.md](roundI_cached/summary.md). Anchor = round-H
`h10, floor members, 5 bps` (SR 0.84 / CAGR 15.0% / MDD −31.5% / hold 8.8).

| lever | SR | CAGR | MDD | gross | hold |
|---|---|---|---|---|---|
| h10 + barrier m 2.0 | **0.85** | 15.4% | -30.6% | 0.78 | 9.5 |
| h10 + fill_max 1.5 | 0.84 | 16.5% | -31.6% | 0.83 | 8.8 |
| h10 + fill_max 2.0 | 0.82 | 16.9% | -33.6% | 0.87 | 8.8 |
| **h7, h20 members, fill_max 2.0** | 0.83 | **17.8%** | -30.8% | 0.85 | **6.2** |
| h7 + fill_max 1.5 | 0.82 | 16.1% | -29.9% | 0.83 | 6.1 |
| h10 + vol target 25% | 0.83 | 16.4% | -34.8% | 0.84 | 8.8 |
| h10 + vol target 30% | 0.80 | 16.9% | -39.6% | 0.88 | 8.8 |
| h10, top-7 / h7, top-7 / top-10 | 0.81-0.83 | 13.7-14.5% | -31..-33% | 0.79-0.81 | — |
| h10, earnings skip off | 0.84 | 14.9% | -30.1% | 0.77 | 8.8 |
| h10 + dead-money exit at 5 | 0.78 | 13.8% | -30.0% | 0.76 | 6.7 |
| h10 / h7 + barrier m 1.0 | 0.75 / 0.65 | 12.7% / 10.6% | -33% | 0.73 | 7.0 / 4.9 |
| h5, h20 members, fill 2.0 | 0.73 | 15.1% | -36.9% | 0.84 | 4.4 |
| "best" combos (fill 2.0 + vt 25%) | 0.80 | 17.4-17.5% | -34..-37% | 0.90 | — |
| the same at 10 bps | 0.69-0.73 | 14.6-15.4% | -36..-38% | 0.89 | — |
| h40 floor + fill 2.0, 15 bps (control) | 0.78 | 18.2% | **-53.4%** | 0.97 | 34.7 |

Readings:

- **`fill_max` does what it was built for**: +6-10pp of invested capital and
  +1.5-2pp CAGR at h7/h10 for ≤0.02 Sharpe; 1.5 is the better trade, 2.0 starts
  to cost drawdown. On the 40-session book it is harmful (−53% MDD): at long
  holds the freed capital is re-deployed *into* drawdowns.
- **Widening the barrier at h10 (m 2.0) helps, tightening (m 1.0) hurts**: at a
  10-session horizon the fixed ±1.5σ√10 stop already fires on noise; letting the
  vertical do more of the exiting is better. Lower m at h7 is the worst variant.
- **More names does not help** (top-7/10 lower CAGR, same drawdown) — the top of
  the ranking carries the return, as rounds A-F found.
- **Raising the vol target buys CAGR with drawdown** one-for-one; not free.
- **The one-week candidate**: h7, `lgbm_h20`+`gru_h20`, top-5, vt 20%,
  fill_max 1.5-2.0, earnings skip: SR 0.82-0.83, CAGR 16-18%, MDD −30/−31%,
  6 sessions average hold — vs the adopted 40-session book's 0.71 / 14.0% /
  −45% on the same scores and cost convention (15 bps there, 5 bps here).
  At 10 bps it is 0.69; **the cost measurement decides**.

## 2c. The refreshed production-style book (stage1 → stage2 → stage3 with the tail fold)

Same config as production except the partial final fold; models retrained on
the 2026-09-04 snapshot. Ungated event book, active window, 15 bps:

| | production (2026-09-01) | fresh (2026-09-07) |
|---|---|---|
| entries | 2007-01-10 → **2026-01-21** | 2007-01-10 → **2026-09-03** |
| last exit | 2026-03-20 | 2026-09-04 (206 positions still open, `censored`) |
| trades | 23,129 | 24,020 |
| Sharpe / CAGR / MDD | 0.69 / 13.3% / −45% | 0.79 / 16.2% / −45% |
| CPCV median Sharpe | 0.91 | 0.87 |
| 2026 entries, avg net trade, win | 65, −2.7%, 35% | 815, **+5.1%**, 52% |

The March cutoff is gone. The higher full-period Sharpe is partly the newer
snapshot (the repo documents a ±0.1 band between pulls) and partly 2026, which
the old run barely saw. Member Rank ICs on the fresh run: lgbm_h60 0.028,
lgbm_h20 0.022, gru_h60 0.019, gru_h5 0.016, gru_h20 0.015, **cnn 0.004,
lgbm_h5 −0.027** — the floor finding stands. Per-year table:
[stage3_fresh/by_year.md](stage3_fresh/by_year.md).

## 2d. Round J — the same candidates on the FRESH scores (the decisive test)

Full table: [roundJ_fresh/summary.md](roundJ_fresh/summary.md). Every variant
below was run on the 2026-09-01 cached scores (rounds H/I) and again on the
2026-09-07 tail-coverage scores — two independent model fits of the same
config. A real improvement has to survive both.

| variant | SR cached → fresh | CAGR cached → fresh | MDD cached → fresh | hold |
|---|---|---|---|---|
| adopted book, 7 members, 15 bps | 0.71 → 0.79 | 14.0% → 16.5% | −45% → −45% | 34.5 |
| floor members | 0.81 → 0.79 | 17.3% → 17.8% | −45% → −46% | 34.6 |
| floor, 5 bps | 0.86 → 0.84 | 18.6% → 19.1% | −45% → −46% | 34.6 |
| **floor + trailing stop 1.0σ√h** | **0.86 → 0.84** | 17.1% → 17.7% | **−40% → −42%** | **28.1** |
| **floor + dead-money exit at 20** | **0.84 → 0.84** | 17.3% → 18.0% | **−41% → −42%** | **27.0** |
| h10, 5 bps | 0.84 → **0.72** | 15.0% → 12.6% | −32% → **−42%** | 8.8 |
| h10, 5 bps, fill 1.5 | 0.84 → 0.71 | 16.5% → 13.7% | −32% → −43% | 8.8 |
| h7, 5 bps | 0.83 → **0.66** | 14.7% → 11.4% | −28% → **−40%** | 6.2 |
| h7, h20 members, fill 2.0 | 0.83 → 0.69 | 17.8% → 14.1% | −31% → −43% | 6.2 |
| h5, 5 bps | 0.71 → 0.53 | 12.3% → 8.5% | −35% → −43% | 4.4 |
| the h7/h10 candidates at 10 bps | — → 0.59-0.63 | — → 11-12% | — → −45..−47% | — |

Where the short-cycle loss comes from (per-year series, daily correlation
between the two fits 0.83-0.84 for the short cycles vs 0.87-0.91 for h40): it
is **spread across years**, not one bad period — 2010, 2013, 2014, 2017 and
2025 are 6-15pp lower on the fresh fit, 2022 is −35% instead of −18%. On the
2021-2025 window the short cycles' Sharpe is 0.33-0.39 on the fresh fit against
0.65 for the 40-session floor book. A top-5 book that re-ranks every 7-10
sessions is far more exposed to which particular model got fitted than a book
that holds through 40; the cached-score result was a favourable draw.

**Conclusion.** With this signal, a hold of a week or less is not supported:
its Sharpe swings by 0.12-0.18 between two fits of the same config, its
drawdown advantage disappears, and it still needs ≤5 bps per leg. The
40-session book with a **trailing stop (1.0σ√h) or a dead-money exit at 20
sessions** is the improvement that replicates: ~7 fewer sessions held, 3-4pp
less drawdown, +0.05 Sharpe, CAGR flat to +1pp, on both fits and at the
production cost of 15 bps. The member floor is neutral on the fresh fit
(+1.3pp CAGR, same Sharpe) and stays as M10-03 hygiene. `fill_max` only pays
on the cycles that did not replicate and hurts at h40; not adopted.

## 3. What is being tested next and what still has to happen

- Done: round J on the fresh scores (§2d), stage1 → stage2 → stage3 with the
  tail fold (§2c).
- To adopt the trailing stop or dead-money exit: set `barrier.trail_m: 1.0` (or
  `barrier.flat_k: 20`, `flat_m: 0.5`) in the config and wire those keys through
  `engine_opts_from_cfg` and the M18 order file (the trail is a nightly re-peg
  of the GTC stop; the flat exit is a scheduled MOO). Both are a config-hash
  change, so predict full-refits its champions once.
- Merge to `top150` and run the quarterly refresh (stage1 → stage2 → stage3)
  so the published Backtest page covers up to the last date.
- Separately: the daily ticket still comes from the 15-tranche rotation
  (`construct_targets`), not the event-engine book that was backtested — a
  live/research mismatch that predates this branch.
- Before any change trades real money: paper-trade and measure open-print
  slippage with the console; every cost figure above is an assumption.

## 4. Where things are

| item | location |
|---|---|
| code | merged into `top150` on 2026-09-08 (branch deleted) |
| round H output | `k4cli3aj48:derived/exp_short/exp_roundH_cached/` (+ pod log) |
| round I output | `k4cli3aj48:derived/exp_short/exp_roundI_cached/` |
| round J output (fresh scores) | `k4cli3aj48:derived/exp_short/exp_roundJ_fresh/` |
| stage1/2/3 with tail coverage | `k4cli3aj48:derived/top150/stage{1,2,3}/` — replaced the 2026-09-01 artifacts on merge (old copies live in git history) |
| ranked tables in git | `reports/exp_short/<round>/summary.md` |
