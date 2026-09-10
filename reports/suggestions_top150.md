# Event-engine book for next open (signals @ close 2026-09-08)

- Names: 28, gross long 1.00 (entering 0.01 + held 0.99), budget x0.81, cap scale x0.17
- Heads valid RankIC: lgbm_h5 0.043, lgbm_h20 0.062, lgbm_h60 0.026
- Training: update (warm update on champions (last full fit 2 sessions old)) — lgbm_h5 kept champion, lgbm_h20 kept champion, lgbm_h60 kept champion

| ticker | action | weight | rank | last close | stop % | PT % | trail % | sessions left | levels vs |
|---|---|---|---|---|---|---|---|---|---|
| SBUX | BUY (new lot 0.292% + held 3.694%) | 3.986% | +0.372 | 102.01 | -13.35% | +13.35% | -8.9% | 40 | fill |
| HD | BUY (new lot 0.267% + held 4.537%) | 4.804% | +0.387 | 313.7 | -14.6% | +14.6% | -9.73% | 40 | fill |
| BKNG | BUY (new lot 0.147%) | 0.147% | +0.415 | 180.3 | -26.47% | +26.47% | -17.65% | 40 | fill |
| MPWR | BUY (new lot 0.146% + held 15.447%) | 15.593% | +0.393 | 1218.5 | -26.69% | +26.69% | -17.79% | 40 | fill |
| COIN | BUY (new lot 0.081% + held 10.613%) | 10.694% | +0.369 | 178.94 | -47.99% | +47.99% | -32.0% | 40 | fill |
| CAT | HOLD (1 lot) | 0.502% | +0.099 | 822.48 | -14.47% | +22.42% | -13.62% | 33 | last close |
| CEG | HOLD (2 lots) | 3.310% | +0.080 | 299.05 | -13.52% | +11.67% | -14.28% | 16 | last close |
| CIEN | HOLD (12 lots) | 5.273% | +0.216 | 341.29 | -9.36% | +61.91% | -32.77% | 13 | last close |
| COF | HOLD (5 lots) | 2.924% | +0.361 | 213.96 | -5.32% | +13.88% | -10.7% | 23 | last close |
| COHR | HOLD (8 lots) | 2.227% | +0.193 | 301.88 | -17.43% | +31.64% | -38.51% | 10 | last close |
| CRWD | HOLD (2 lots) | 2.562% | +0.313 | 210.02 | -11.5% | +18.87% | -33.23% | 29 | last close |
| CVNA | HOLD (4 lots) | 1.242% | nan | 74.72 | -22.1% | +12.98% | -21.5% | 4 | last close |
| DDOG | HOLD (1 lot) | 0.524% | +0.299 | 210.23 | -24.21% | +80.58% | -28.59% | 22 | last close |
| DELL | HOLD (2 lots) | 1.457% | +0.019 | 533.88 | -29.4% | +20.29% | -33.62% | 21 | last close |
| FDX | HOLD (6 lots) | 4.329% | nan | 314.13 | -2.77% | +13.47% | -10.33% | 5 | last close |
| FIX | HOLD (19 lots) | 13.960% | +0.132 | 1648.47 | -12.36% | +28.8% | -20.8% | 1 | last close |
| FLEX | HOLD (3 lots) | 1.606% | nan | 114.31 | -20.43% | +57.12% | -23.03% | 15 | last close |
| HOOD | HOLD (8 lots) | 3.273% | +0.352 | 117.34 | -17.45% | +8.81% | -34.5% | 9 | last close |
| LIN | HOLD (3 lots) | 5.505% | +0.299 | 468.38 | -5.06% | +16.96% | -7.59% | 21 | last close |
| LITE | HOLD (4 lots) | 1.847% | +0.215 | 978.53 | -34.36% | +7.74% | -38.67% | 2 | last close |
| LRCX | HOLD (3 lots) | 0.440% | +0.165 | 320.42 | -25.51% | +22.85% | -25.58% | 34 | last close |
| MCHP | HOLD (8 lots) | 4.112% | +0.218 | 73.38 | -9.62% | +44.19% | -19.24% | 1 | last close |
| MCK | HOLD (3 lots) | 3.950% | +0.281 | 889.12 | -6.6% | +4.63% | -12.25% | 1 | last close |
| PLTR | HOLD (1 lot) | 0.508% | +0.274 | 170.3 | -28.53% | +48.99% | -30.05% | 39 | last close |
| STX | HOLD (2 lots) | 0.545% | +0.214 | 904.38 | -25.93% | +25.54% | -29.24% | 37 | last close |
| TJX | HOLD (1 lot) | 1.128% | +0.089 | 128.92 | -1.25% | +27.94% | -9.65% | 27 | last close |
| VRT | HOLD (1 lot) | 0.934% | +0.224 | 290.83 | -27.86% | +26.76% | -24.68% | 29 | last close |
| VST | HOLD (5 lots) | 2.617% | nan | 151.72 | -13.93% | +25.12% | -15.56% | 10 | last close |
| AZO | SELL at open | 0 |  | 2951.61 |  |  |  | 0 | vertical barrier: MOO sell at the next o |
| FIX | SELL at open | 0 |  | 1648.47 |  |  |  | 0 | vertical barrier: MOO sell at the next o |
| MCHP | SELL at open | 0 |  | 73.38 |  |  |  | 0 | vertical barrier: MOO sell at the next o |

_Vertical exit: MOO 40 sessions after entry. Trailing stop: each night raise the stop to the high since fill minus trail %, never below the fixed stop. HOLD rows price the most binding lot's levels off the last close. Research tooling, not financial advice._