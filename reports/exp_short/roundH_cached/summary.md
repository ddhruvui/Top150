# Experiment round H (cached 2026-09-01 scores, top-150)

- stamp: `{"config_hash": "9468aeae724febd52b0e822fc0419c610e0edf2ec6a33482558ee09081a821ed", "data_snapshot_id": "fb47fe61409eeedb", "git_sha": "unknown", "seed": 20260717}`
- variants: 27 · trials ledger N: 317
- anchor: **H0_book_all7** — SR 0.71, CAGR 14.0%, MDD -45.0%, hold 34.7

| # | variant | SR | CAGR | MDD | vol | hold | trades | win | gross | cost/yr | 3y CAGR | 3y SR | 5y CAGR | h | bps | mem | exit mix | levers |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | H1_floor_c5 | 0.86 | 18.6% | -44.6% | 22.9% | 34.7 | 22,744 | 59.6% | 0.92 | 0.6% | 31.9% | 1.12 | 14.1% | 40 | 5 | 4 | uppe 20% lowe 12% vert 69% cens 0% | top_n=5 |
| 2 | H1_floor_trail10 | 0.86 | 17.1% | -40.0% | 20.9% | 27.9 | 21,751 | 50.1% | 0.87 | 2.2% | 32.3% | 1.25 | 14.4% | 40 | 15 | 4 | uppe 18% lowe 0% trai 43% vert 40% cens 0% | trail_m=1.0, top_n=5 |
| 3 | H2_h10_c5 | 0.84 | 15.0% | -31.5% | 18.8% | 8.8 | 22,527 | 55.1% | 0.77 | 1.6% | 24.0% | 1.20 | 8.6% | 10 | 5 | 4 | uppe 15% lowe 12% vert 73% cens 0% | skip_earnings=True, top_n=5 |
| 4 | H1_floor_flat20 | 0.84 | 17.3% | -40.9% | 22.0% | 27.0 | 22,901 | 56.2% | 0.89 | 2.0% | 33.0% | 1.19 | 15.7% | 40 | 15 | 4 | uppe 17% lowe 10% flat 40% vert 33% cens 0% | flat_k=20, top_n=5 |
| 5 | H2_h10_c5_conv | 0.83 | 15.1% | -32.2% | 19.1% | 8.8 | 22,531 | 55.1% | 0.75 | 1.5% | 26.3% | 1.27 | 9.9% | 10 | 5 | 4 | uppe 15% lowe 12% vert 73% cens 0% | conv_weight=linear, skip_earnings=True, top_n=5 |
| 6 | H3_h7_c5 | 0.83 | 14.7% | -28.3% | 18.7% | 6.1 | 22,549 | 54.3% | 0.76 | 2.1% | 23.8% | 1.20 | 8.7% | 7 | 5 | 4 | uppe 14% lowe 12% vert 74% cens 0% | skip_earnings=True, top_n=5 |
| 7 | H1_floor_trend | 0.82 | 17.6% | -41.0% | 23.0% | 34.4 | 6,603 | 59.5% | 0.82 | 1.7% | 32.8% | 1.19 | 12.9% | 40 | 15 | 4 | uppe 20% lowe 11% vert 69% cens 0% | trend=sma20_60, top_n=5 |
| 8 | H1_floor_flat10 | 0.82 | 16.6% | -37.8% | 21.5% | 23.1 | 22,971 | 55.5% | 0.87 | 2.2% | 32.8% | 1.22 | 13.3% | 40 | 15 | 4 | uppe 14% lowe 8% flat 42% vert 35% cens 0% | flat_k=10, top_n=5 |
| 9 | H1_floor_earn | 0.82 | 17.4% | -45.0% | 22.9% | 34.7 | 22,169 | 59.2% | 0.92 | 1.7% | 30.7% | 1.09 | 12.8% | 40 | 15 | 4 | uppe 20% lowe 12% vert 68% cens 0% | skip_earnings=True, top_n=5 |
| 10 | H2_h10_c5_h20only | 0.82 | 14.6% | -26.7% | 18.9% | 8.8 | 22,530 | 55.7% | 0.76 | 1.6% | 19.6% | 1.00 | 7.1% | 10 | 5 | 2 | uppe 15% lowe 12% vert 73% cens 0% | skip_earnings=True, top_n=5 |
| 11 | H1_floor | 0.81 | 17.3% | -45.0% | 22.9% | 34.7 | 22,744 | 59.0% | 0.92 | 1.7% | 30.2% | 1.08 | 12.6% | 40 | 15 | 4 | uppe 20% lowe 12% vert 69% cens 0% | top_n=5 |
| 12 | H1_floor_conv | 0.81 | 17.7% | -46.1% | 23.6% | 34.7 | 22,788 | 59.1% | 0.91 | 1.7% | 29.9% | 1.03 | 12.7% | 40 | 15 | 4 | uppe 20% lowe 12% vert 68% cens 0% | conv_weight=linear, top_n=5 |
| 13 | H2_h20_floor | 0.80 | 15.1% | -37.5% | 19.9% | 17.5 | 23,062 | 55.7% | 0.83 | 2.8% | 25.0% | 1.14 | 10.5% | 20 | 15 | 4 | uppe 16% lowe 12% vert 71% cens 0% | top_n=5 |
| 14 | H3_h5_c5_top10 | 0.77 | 12.9% | -33.4% | 17.7% | 4.4 | 45,521 | 53.4% | 0.80 | 2.7% | 13.9% | 0.78 | 3.1% | 5 | 5 | 2 | uppe 13% lowe 12% vert 75% cens 0% | skip_earnings=True, top_n=10 |
| 15 | H2_h10_c5_trail | 0.77 | 13.0% | -33.4% | 17.9% | 7.0 | 22,432 | 47.9% | 0.73 | 2.2% | 22.8% | 1.20 | 7.7% | 10 | 5 | 4 | uppe 13% lowe 0% trai 44% vert 43% cens 0% | trail_m=1.0, skip_earnings=True, top_n=5 |
| 16 | H0_book_nocnn | 0.76 | 16.0% | -43.5% | 22.9% | 34.7 | 22,951 | 58.2% | 0.92 | 1.8% | 22.6% | 0.92 | 4.9% | 40 | 15 | 6 | uppe 19% lowe 12% vert 69% cens 0% | top_n=5 |
| 17 | H2_h10_c10 | 0.76 | 13.3% | -32.4% | 18.8% | 8.8 | 22,527 | 54.5% | 0.77 | 3.1% | 21.9% | 1.12 | 6.7% | 10 | 10 | 4 | uppe 15% lowe 12% vert 73% cens 0% | skip_earnings=True, top_n=5 |
| 18 | H1_floor_trail07 | 0.74 | 13.3% | -46.3% | 19.5% | 20.4 | 20,994 | 42.7% | 0.81 | 3.0% | 24.0% | 1.07 | 9.6% | 40 | 15 | 4 | uppe 14% lowe 0% trai 67% vert 20% cens 0% | trail_m=0.7, top_n=5 |
| 19 | H3_h7_c10 | 0.72 | 12.4% | -29.9% | 18.7% | 6.1 | 22,549 | 53.5% | 0.76 | 4.1% | 21.1% | 1.09 | 6.1% | 7 | 10 | 4 | uppe 14% lowe 12% vert 74% cens 0% | skip_earnings=True, top_n=5 |
| 20 | H3_h5_c5 | 0.71 | 12.3% | -35.2% | 18.8% | 4.4 | 22,544 | 53.5% | 0.74 | 2.7% | 15.5% | 0.83 | 3.4% | 5 | 5 | 2 | uppe 13% lowe 12% vert 75% cens 0% | skip_earnings=True, top_n=5 |
| 21 | H0_book_all7 | 0.71 | 14.0% | -45.0% | 21.9% | 34.7 | 22,797 | 57.6% | 0.93 | 1.9% | 19.8% | 0.87 | 4.3% | 40 | 15 | 7 | uppe 19% lowe 12% vert 68% cens 0% | top_n=5 |
| 22 | H2_h10_c15 | 0.67 | 11.5% | -33.3% | 18.8% | 8.8 | 22,527 | 54.0% | 0.77 | 4.7% | 19.9% | 1.03 | 4.8% | 10 | 15 | 4 | uppe 15% lowe 12% vert 73% cens 0% | skip_earnings=True, top_n=5 |
| 23 | H3_h5_c5_fast4 | 0.67 | 11.3% | -31.1% | 18.6% | 4.4 | 22,901 | 53.4% | 0.75 | 3.1% | 10.6% | 0.62 | 2.4% | 5 | 5 | 4 | uppe 13% lowe 12% vert 75% cens 0% | skip_earnings=True, top_n=5 |
| 24 | H2_h10_c5_combo | 0.62 | 10.5% | -41.6% | 18.7% | 7.2 | 7,927 | 47.1% | 0.58 | 1.7% | 26.3% | 1.33 | 5.9% | 10 | 5 | 4 | uppe 11% lowe 0% trai 44% vert 45% | trail_m=1.0, trend=sma20_60, conv_weight=linear, skip_earnings=True, top_n=5 |
| 25 | H2_h10_c5_trend | 0.62 | 10.8% | -44.9% | 19.6% | 8.9 | 8,020 | 54.6% | 0.64 | 1.5% | 24.7% | 1.22 | 3.6% | 10 | 5 | 4 | uppe 13% lowe 12% vert 76% cens 0% | trend=sma20_60, skip_earnings=True, top_n=5 |
| 26 | H3_h5_c10 | 0.57 | 9.3% | -37.0% | 18.8% | 4.4 | 22,544 | 52.6% | 0.74 | 5.5% | 12.6% | 0.70 | 0.3% | 5 | 10 | 2 | uppe 13% lowe 12% vert 75% cens 0% | skip_earnings=True, top_n=5 |
| 27 | H3_h5_c5_combo | 0.33 | 4.6% | -43.8% | 18.5% | 3.7 | 8,040 | 47.3% | 0.53 | 3.0% | 9.7% | 0.56 | -3.0% | 5 | 5 | 2 | uppe 9% lowe 0% trai 40% vert 50% cens 0% | trail_m=1.0, trend=sma20_60, conv_weight=linear, skip_earnings=True, top_n=5 |

## Deltas vs H0_book_all7

| variant | dSR | dCAGR | dMDD | dhold | d3y CAGR |
|---|---|---|---|---|---|
| H1_floor_c5 | +0.15 | +4.6pp | +0.3pp | -0.0 | +12.1pp |
| H1_floor_trail10 | +0.15 | +3.1pp | +5.0pp | -6.8 | +12.5pp |
| H2_h10_c5 | +0.13 | +1.0pp | +13.5pp | -25.9 | +4.2pp |
| H1_floor_flat20 | +0.13 | +3.3pp | +4.1pp | -7.7 | +13.2pp |
| H2_h10_c5_conv | +0.12 | +1.1pp | +12.7pp | -25.9 | +6.5pp |
| H3_h7_c5 | +0.12 | +0.7pp | +16.7pp | -28.5 | +4.0pp |
| H1_floor_trend | +0.11 | +3.6pp | +3.9pp | -0.3 | +13.0pp |
| H1_floor_flat10 | +0.11 | +2.6pp | +7.1pp | -11.6 | +13.0pp |
| H1_floor_earn | +0.11 | +3.4pp | -0.0pp | +0.0 | +11.0pp |
| H2_h10_c5_h20only | +0.11 | +0.6pp | +18.2pp | -25.9 | -0.2pp |
| H1_floor | +0.10 | +3.3pp | -0.0pp | -0.0 | +10.4pp |
| H1_floor_conv | +0.10 | +3.7pp | -1.2pp | -0.0 | +10.1pp |
| H2_h20_floor | +0.09 | +1.0pp | +7.4pp | -17.1 | +5.3pp |
| H3_h5_c5_top10 | +0.06 | -1.1pp | +11.6pp | -30.3 | -5.9pp |
| H2_h10_c5_trail | +0.06 | -1.0pp | +11.6pp | -27.6 | +3.0pp |
| H0_book_nocnn | +0.05 | +2.0pp | +1.5pp | +0.0 | +2.8pp |
| H2_h10_c10 | +0.05 | -0.7pp | +12.6pp | -25.9 | +2.1pp |
| H1_floor_trail07 | +0.03 | -0.7pp | -1.3pp | -14.3 | +4.2pp |
| H3_h7_c10 | +0.01 | -1.6pp | +15.0pp | -28.5 | +1.3pp |
| H3_h5_c5 | +0.00 | -1.7pp | +9.8pp | -30.3 | -4.3pp |
| H2_h10_c15 | -0.03 | -2.5pp | +11.7pp | -25.9 | +0.1pp |
| H3_h5_c5_fast4 | -0.04 | -2.7pp | +13.9pp | -30.3 | -9.2pp |
| H2_h10_c5_combo | -0.08 | -3.6pp | +3.4pp | -27.4 | +6.5pp |
| H2_h10_c5_trend | -0.09 | -3.2pp | +0.1pp | -25.7 | +4.9pp |
| H3_h5_c10 | -0.14 | -4.7pp | +8.0pp | -30.3 | -7.2pp |
| H3_h5_c5_combo | -0.38 | -9.4pp | +1.2pp | -31.0 | -10.1pp |

_Net of the per-variant cost assumption; walk-forward, scored window only. Research tooling under the repo's own gates — not financial advice._
