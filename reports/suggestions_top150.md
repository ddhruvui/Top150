# Event-engine book for next open (signals @ close 2026-09-10)

- Names: 29, gross long 1.00 (entering 0.06 + held 0.94), budget x1.04, cap scale x0.87
- Heads valid RankIC: lgbm_h5 0.040, lgbm_h20 0.058, lgbm_h60 0.034
- Training: update (warm update on champions (last full fit 4 sessions old)) — lgbm_h5 kept champion, lgbm_h20 kept champion, lgbm_h60 kept champion

| ticker | action | weight | rank | last close | stop % | PT % | trail % | sessions left | levels vs |
|---|---|---|---|---|---|---|---|---|---|
| SBUX | BUY (new lot 1.548% + held 5.637%) | 7.185% | +0.367 | 99.22 | -13.43% | +13.43% | -8.95% | 40 | fill |
| AZO | BUY (new lot 1.453% + held 14.136%) | 15.589% | +0.458 | 2881.47 | -14.31% | +14.31% | -9.54% | 40 | fill |
| HD | BUY (new lot 1.446% + held 7.256%) | 8.702% | +0.384 | 305.69 | -14.38% | +14.38% | -9.58% | 40 | fill |
| DASH | BUY (new lot 0.832%) | 0.832% | +0.409 | 201.03 | -24.99% | +24.99% | -16.66% | 40 | fill |
| ADBE | BUY (new lot 0.709%) | 0.709% | +0.395 | 248.83 | -29.34% | +29.34% | -19.56% | 40 | fill |
| AMAT | HOLD (2 lots) | 0.782% | +0.104 | 454.01 | -16.79% | +52.3% | -23.13% | 9 | last close |
| APP | HOLD (1 lot) | 0.721% | +0.290 | 314.49 | -23.1% | +29.9% | -23.61% | 39 | last close |
| CEG | HOLD (2 lots) | 3.088% | +0.123 | 285.97 | -9.57% | +16.78% | -14.31% | 14 | last close |
| CIEN | HOLD (9 lots) | 3.153% | +0.223 | 334.56 | -7.54% | +65.16% | -30.86% | 22 | last close |
| CMCSA | HOLD (1 lot) | 0.023% | +0.167 | 25.17 | -9.94% | +21.83% | -15.4% | 13 | last close |
| COHR | HOLD (6 lots) | 1.838% | +0.185 | 293.17 | -24.02% | +54.93% | -36.58% | 11 | last close |
| COIN | HOLD (18 lots) | 9.568% | +0.243 | 172.28 | -13.99% | +16.88% | -30.35% | 13 | last close |
| CRWD | HOLD (3 lots) | 2.192% | +0.163 | 208.86 | -11.01% | +19.53% | -31.26% | 26 | last close |
| CVNA | HOLD (3 lots) | 1.175% | nan | 70.28 | -17.18% | +24.38% | -21.47% | 2 | last close |
| DE | HOLD (2 lots) | 2.192% | +0.009 | 677.94 | -7.56% | +5.32% | -14.07% | 20 | last close |
| DELL | HOLD (2 lots) | 1.145% | +0.087 | 506.62 | -22.22% | +26.77% | -32.72% | 19 | last close |
| FDX | HOLD (2 lots) | 0.971% | nan | 311.8 | -2.39% | +16.1% | -10.08% | 3 | last close |
| FIX | HOLD (5 lots) | 3.395% | +0.297 | 1590.81 | -9.18% | +36.49% | -19.92% | 1 | last close |
| FLEX | HOLD (2 lots) | 0.691% | nan | 108.01 | -17.27% | +69.72% | -22.72% | 13 | last close |
| GLW | HOLD (1 lot) | 0.075% | -0.113 | 163.12 | -36.67% | +42.76% | -27.86% | 11 | last close |
| HOOD | HOLD (5 lots) | 2.537% | +0.361 | 113.33 | -14.53% | +12.66% | -32.63% | 22 | last close |
| JNJ | HOLD (1 lot) | 0.629% | +0.072 | 266.35 | -4.1% | +13.44% | -8.8% | 31 | last close |
| LIN | HOLD (3 lots) | 5.178% | +0.330 | 461.62 | -3.67% | +18.67% | -7.35% | 19 | last close |
| LITE | HOLD (13 lots) | 4.217% | +0.319 | 935.7 | -29.97% | +42.86% | -37.37% | 18 | last close |
| MCD | HOLD (1 lot) | 2.468% | +0.171 | 253.05 | -0.78% | +21.23% | -7.38% | 14 | last close |
| MDT | HOLD (2 lots) | 2.732% | +0.051 | 91.62 | -7.35% | +8.86% | -8.99% | 16 | last close |
| MPWR | HOLD (27 lots) | 15.992% | +0.206 | 1186.08 | -1.11% | +28.89% | -16.97% | 1 | last close |
| TER | HOLD (1 lot) | 0.647% | +0.218 | 370.19 | -27.63% | +64.53% | -27.62% | 15 | last close |
| VST | HOLD (3 lots) | 1.575% | nan | 147.05 | -12.92% | +29.1% | -15.23% | 9 | last close |
| FIX | SELL at open | 0 |  | 1590.81 |  |  |  | 0 | vertical barrier: MOO sell at the next o |
| MCK | SELL at open | 0 |  | 880.86 |  |  |  | 0 | vertical barrier: MOO sell at the next o |
| MPWR | SELL at open | 0 |  | 1186.08 |  |  |  | 0 | vertical barrier: MOO sell at the next o |

_Vertical exit: MOO 40 sessions after entry. Trailing stop: each night raise the stop to the high since fill minus trail %, never below the fixed stop. HOLD rows price the most binding lot's levels off the last close. Research tooling, not financial advice._