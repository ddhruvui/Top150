# Experiment round K (2026-09-08 fit: trail on vs off, paired)

- stamp: `{"config_hash": "d7893b1950b0e1322d6ee5c48234bb4c1189833ec8f8c0d253b905324fcae9e8", "data_snapshot_id": "fb47fe61409eeedb", "git_sha": "unknown", "seed": 20260717}`
- variants: 4 · trials ledger N: 816
- anchor: **K_trail_off** — SR 0.74, CAGR 15.2%, MDD -45.5%, hold 34.4

| # | variant | SR | CAGR | MDD | vol | hold | trades | win | gross | cost/yr | 3y CAGR | 3y SR | 5y CAGR | h | bps | mem | exit mix | levers |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | K_trail_on_floor | 0.86 | 18.0% | -37.7% | 22.2% | 27.7 | 22,290 | 50.9% | 0.86 | 2.3% | 42.6% | 1.23 | 20.8% | 40 | 15 | 4 | uppe 18% trai 42% vert 38% cens 1% | top_n=5 |
| 2 | K_trail_off_floor | 0.84 | 19.2% | -42.3% | 24.5% | 34.3 | 23,427 | 59.5% | 0.91 | 1.7% | 46.8% | 1.19 | 22.5% | 40 | 15 | 4 | uppe 21% lowe 12% vert 67% cens 1% | top_n=5 |
| 3 | K_trail_on_cfg | 0.75 | 14.2% | -41.6% | 20.7% | 27.5 | 22,788 | 49.2% | 0.88 | 2.4% | 25.4% | 0.93 | 9.3% | 40 | 15 | 7 | uppe 18% lowe 0% trai 43% vert 38% cens 1% | top_n=5 |
| 4 | K_trail_off | 0.74 | 15.2% | -45.5% | 22.6% | 34.4 | 23,520 | 57.7% | 0.92 | 1.9% | 30.1% | 0.98 | 11.8% | 40 | 15 | 7 | uppe 20% lowe 12% vert 67% cens 1% | top_n=5 |

## Deltas vs K_trail_off

| variant | dSR | dCAGR | dMDD | dhold | d3y CAGR |
|---|---|---|---|---|---|
| K_trail_on_floor | +0.12 | +2.8pp | +7.8pp | -6.7 | +12.5pp |
| K_trail_off_floor | +0.10 | +4.0pp | +3.3pp | -0.1 | +16.7pp |
| K_trail_on_cfg | +0.01 | -1.0pp | +3.9pp | -6.9 | -4.7pp |

_Net of the per-variant cost assumption; walk-forward, scored window only. Research tooling under the repo's own gates — not financial advice._
