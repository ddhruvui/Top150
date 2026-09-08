# Experiment round J (FRESH tail-coverage scores, 2026-09-07 stage2, top-150)

- stamp: `{"config_hash": "9468aeae724febd52b0e822fc0419c610e0edf2ec6a33482558ee09081a821ed", "data_snapshot_id": "fb47fe61409eeedb", "git_sha": "unknown", "seed": 20260717}`
- variants: 16 · trials ledger N: 563
- anchor: **J0_book_all7** — SR 0.79, CAGR 16.5%, MDD -45.0%, hold 34.5

| # | variant | SR | CAGR | MDD | vol | hold | trades | win | gross | cost/yr | 3y CAGR | 3y SR | 5y CAGR | h | bps | mem | exit mix | levers |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | J1_floor_trail10 | 0.84 | 17.7% | -41.8% | 22.2% | 28.1 | 22,446 | 51.1% | 0.86 | 2.2% | 32.5% | 1.06 | 15.0% | 40 | 15 | 4 | uppe 18% trai 41% vert 40% cens 1% | trail_m=1.0, top_n=5 |
| 2 | J1_floor_c5 | 0.84 | 19.1% | -45.9% | 24.4% | 34.6 | 23,361 | 59.7% | 0.91 | 0.6% | 38.6% | 1.09 | 18.4% | 40 | 5 | 4 | uppe 20% lowe 12% vert 68% cens 1% | top_n=5 |
| 3 | J1_floor_flat20 | 0.84 | 18.0% | -41.5% | 22.9% | 27.0 | 23,584 | 55.9% | 0.88 | 2.0% | 41.0% | 1.22 | 19.4% | 40 | 15 | 4 | uppe 17% lowe 10% flat 40% vert 33% cens 1% | flat_k=20, top_n=5 |
| 4 | J1_floor | 0.79 | 17.8% | -46.2% | 24.4% | 34.6 | 23,346 | 59.2% | 0.91 | 1.7% | 37.0% | 1.06 | 16.9% | 40 | 15 | 4 | uppe 20% lowe 12% vert 68% cens 1% | top_n=5 |
| 5 | J0_book_all7 | 0.79 | 16.5% | -45.0% | 22.5% | 34.5 | 23,498 | 58.3% | 0.92 | 1.9% | 26.2% | 0.93 | 9.6% | 40 | 15 | 7 | uppe 20% lowe 12% vert 67% cens 1% | top_n=5 |
| 6 | J2_h10_c5 | 0.72 | 12.6% | -42.0% | 19.1% | 8.8 | 23,224 | 54.4% | 0.75 | 1.5% | 20.1% | 0.97 | 5.1% | 10 | 5 | 4 | uppe 14% lowe 12% vert 73% cens 0% | skip_earnings=True, top_n=5 |
| 7 | J2_h10_c5_fill15_m20 | 0.72 | 14.3% | -40.5% | 22.1% | 9.5 | 23,231 | 54.5% | 0.84 | 1.4% | 20.7% | 0.81 | 5.4% | 10 | 5 | 4 | uppe 6% lowe 6% vert 88% cens 0% | skip_earnings=True, top_n=5 |
| 8 | J2_h10_c5_fill15 | 0.71 | 13.7% | -43.4% | 21.3% | 8.8 | 23,211 | 54.4% | 0.82 | 1.7% | 20.9% | 0.85 | 5.0% | 10 | 5 | 4 | uppe 14% lowe 12% vert 73% cens 0% | skip_earnings=True, top_n=5 |
| 9 | J3_h7_h20only_fill20 | 0.69 | 14.1% | -43.3% | 23.0% | 6.2 | 23,149 | 53.7% | 0.85 | 2.4% | 27.4% | 0.90 | 6.0% | 7 | 5 | 2 | uppe 13% lowe 12% vert 75% cens 0% | skip_earnings=True, top_n=5 |
| 10 | J3_h7_h20only_fill15 | 0.68 | 13.1% | -44.4% | 21.3% | 6.2 | 23,183 | 53.7% | 0.81 | 2.3% | 22.8% | 0.88 | 3.9% | 7 | 5 | 2 | uppe 13% lowe 12% vert 75% cens 0% | skip_earnings=True, top_n=5 |
| 11 | J3_h7_c5 | 0.66 | 11.4% | -40.4% | 19.2% | 6.2 | 23,229 | 53.4% | 0.75 | 2.0% | 17.4% | 0.87 | 3.8% | 7 | 5 | 4 | uppe 13% lowe 12% vert 74% cens 0% | skip_earnings=True, top_n=5 |
| 12 | J3_h7_c5_fill15 | 0.65 | 12.3% | -43.1% | 21.5% | 6.2 | 23,211 | 53.4% | 0.81 | 2.2% | 16.4% | 0.71 | 2.2% | 7 | 5 | 4 | uppe 13% lowe 12% vert 74% cens 0% | skip_earnings=True, top_n=5 |
| 13 | J2_h10_c10_fill15 | 0.63 | 11.8% | -45.4% | 21.3% | 8.8 | 23,211 | 53.9% | 0.82 | 3.3% | 19.1% | 0.79 | 3.2% | 10 | 10 | 4 | uppe 14% lowe 12% vert 73% cens 0% | skip_earnings=True, top_n=5 |
| 14 | J3_h7_h20only_fill20_c10 | 0.59 | 11.4% | -46.8% | 23.0% | 6.2 | 23,144 | 52.9% | 0.85 | 4.8% | 24.6% | 0.83 | 3.3% | 7 | 10 | 2 | uppe 13% lowe 12% vert 75% cens 0% | skip_earnings=True, top_n=5 |
| 15 | J4_h5_c5_fill20 | 0.55 | 10.5% | -44.9% | 23.1% | 4.4 | 23,126 | 52.6% | 0.84 | 3.1% | 26.2% | 0.87 | 4.7% | 5 | 5 | 2 | uppe 13% lowe 12% vert 75% cens 0% | skip_earnings=True, top_n=5 |
| 16 | J4_h5_c5 | 0.53 | 8.5% | -43.1% | 18.8% | 4.4 | 23,176 | 52.6% | 0.74 | 2.8% | 18.4% | 0.91 | 1.5% | 5 | 5 | 2 | uppe 13% lowe 12% vert 75% cens 0% | skip_earnings=True, top_n=5 |

## Deltas vs J0_book_all7

| variant | dSR | dCAGR | dMDD | dhold | d3y CAGR |
|---|---|---|---|---|---|
| J1_floor_trail10 | +0.05 | +1.2pp | +3.1pp | -6.4 | +6.3pp |
| J1_floor_c5 | +0.05 | +2.7pp | -0.9pp | +0.1 | +12.4pp |
| J1_floor_flat20 | +0.05 | +1.6pp | +3.5pp | -7.5 | +14.8pp |
| J1_floor | +0.00 | +1.3pp | -1.2pp | +0.1 | +10.8pp |
| J2_h10_c5 | -0.07 | -3.8pp | +3.0pp | -25.7 | -6.1pp |
| J2_h10_c5_fill15_m20 | -0.08 | -2.2pp | +4.4pp | -25.0 | -5.5pp |
| J2_h10_c5_fill15 | -0.08 | -2.8pp | +1.5pp | -25.7 | -5.3pp |
| J3_h7_h20only_fill20 | -0.10 | -2.3pp | +1.7pp | -28.3 | +1.1pp |
| J3_h7_h20only_fill15 | -0.11 | -3.4pp | +0.5pp | -28.3 | -3.4pp |
| J3_h7_c5 | -0.13 | -5.1pp | +4.6pp | -28.3 | -8.8pp |
| J3_h7_c5_fill15 | -0.14 | -4.1pp | +1.9pp | -28.3 | -9.8pp |
| J2_h10_c10_fill15 | -0.16 | -4.6pp | -0.4pp | -25.7 | -7.1pp |
| J3_h7_h20only_fill20_c10 | -0.20 | -5.0pp | -1.8pp | -28.3 | -1.7pp |
| J4_h5_c5_fill20 | -0.24 | -6.0pp | +0.1pp | -30.1 | -0.0pp |
| J4_h5_c5 | -0.26 | -7.9pp | +1.9pp | -30.1 | -7.8pp |

_Net of the per-variant cost assumption; walk-forward, scored window only. Research tooling under the repo's own gates — not financial advice._
