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

## 3. What is being tested next (round I) and what still has to happen

- `fill_max` 1.5/2.0 on h5/h7/h10; top-7/top-10 at h7; vol target 25/30%;
  barrier width m 1.0/2.0; earnings skip on/off; the same at 10 bps as the
  honest middle case; h40 + fill_max as the control.
- stage2 → stage3 on the tail-coverage fold so the production comparison
  (and the UI's Backtest page, if merged) covers up to the last date.
- Re-run rounds H/I on the fresh stage-2 scores to confirm the ranking holds.
- Before any of this trades: paper-trade the chosen cycle and measure the
  open-print slippage the console records; the 5-bps result stands or falls
  on that number.

## 4. Where things are

| item | location |
|---|---|
| code | branch `exp-short-horizon` (off `top150`) |
| round H output | `k4cli3aj48:derived/exp_short/exp_roundH_cached/` (+ pod log); ran on x3n7kgbbit before the volume correction |
| round I output | `k4cli3aj48:derived/exp_short/exp_roundI_cached/` |
| stage1/2/3 with tail coverage | `k4cli3aj48:derived/exp_short/stage{1,2,3}/` |
| production artifacts (untouched) | `k4cli3aj48:derived/top150/*` |
| ranked tables in git | `reports/exp_short/<round>/summary.md` |
