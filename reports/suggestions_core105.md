# Event-engine book for next open (signals @ close 2026-09-25)

- Long: 18 names, gross 0.86 (entering 0.03 + held 0.83), budget x0.41, cap scale x1.00
- Heads valid RankIC: lgbm_h5 0.052, gru_h5 0.073, lgbm_h20 0.067, gru_h20 0.123, lgbm_h60 0.097, gru_h60 0.165
- Training: full (no stored GRU champion for every admitted GRU head)

| ticker | action | weight | rank | last close | stop % | PT % | trail % | sessions left | levels vs |
|---|---|---|---|---|---|---|---|---|---|
| RKLB | BUY (new lot 0.331% + held 5.963%) | 6.294% | +0.407 | 73.95 | -37.07% | +37.07% | -24.71% | 40 | fill |
| HPE | BUY (new lot 0.286% + held 6.330%) | 6.616% | +0.397 | 62.94 | -42.84% | +42.84% | -28.56% | 40 | fill |
| TER | BUY (new lot 0.283% + held 9.028%) | 9.311% | +0.428 | 398.38 | -43.3% | +43.3% | -28.87% | 40 | fill |
| ASTS | BUY (new lot 0.270% + held 8.153%) | 8.423% | +0.415 | 61.81 | -45.45% | +45.45% | -30.3% | 40 | fill |
| SMCI | BUY (new lot 0.266% + held 7.973%) | 8.239% | +0.424 | 43.26 | -46.05% | +46.05% | -30.7% | 40 | fill |
| COIN | BUY (new lot 0.249% + held 4.533%) | 4.782% | +0.401 | 195.11 | -49.28% | +49.28% | -32.85% | 40 | fill |
| BE | BUY (new lot 0.241% + held 7.017%) | 7.258% | +0.415 | 288.7 | -50.93% | +50.93% | -33.95% | 40 | fill |
| COHR | BUY (new lot 0.236% + held 6.996%) | 7.231% | +0.432 | 295.83 | -52.0% | +52.0% | -34.67% | 40 | fill |
| AAOI | BUY (new lot 0.223% + held 5.830%) | 6.053% | +0.470 | 101.4 | -54.93% | +54.93% | -36.62% | 40 | fill |
| MSTR | BUY (new lot 0.215% + held 3.349%) | 3.564% | +0.421 | 158.61 | -56.92% | +56.92% | -37.95% | 40 | fill |
| MRNA | BUY (new lot 0.102% + held 1.884%) | 1.987% | +0.479 | 198.88 | -119.68% | +119.68% | -79.79% | 40 | fill |
| HOOD | HOLD (16 lots) | 4.143% | +0.376 | 119.4 | -23.32% | +23.54% | -28.5% | 18 | last close |
| LITE | HOLD (33 lots) | 5.965% | +0.368 | 941.65 | -30.41% | +19.66% | -32.41% | 1 | last close |
| MPWR | HOLD (3 lots) | 0.795% | +0.323 | 1367.43 | -19.34% | +35.06% | -21.73% | 2 | last close |
| MRVL | HOLD (4 lots) | 0.602% | +0.289 | 261.93 | -34.22% | +29.12% | -27.47% | 7 | last close |
| SNOW | HOLD (7 lots) | 2.070% | +0.236 | 335.94 | -5.96% | +23.45% | -20.42% | 6 | last close |
| SOFI | HOLD (2 lots) | 0.444% | +0.278 | 16.58 | -13.63% | +52.6% | -17.48% | 4 | last close |
| WDC | HOLD (12 lots) | 2.177% | +0.328 | 456.81 | -24.84% | +44.55% | -25.12% | 1 | last close |
| AAOI | SELL at open | 0 |  | 101.4 |  |  |  | 0 | vertical barrier: MOO sell at the next o |
| ASTS | SELL at open | 0 |  | 61.81 |  |  |  | 0 | vertical barrier: MOO sell at the next o |
| BE | SELL at open | 0 |  | 288.7 |  |  |  | 0 | vertical barrier: MOO sell at the next o |
| COHR | SELL at open | 0 |  | 295.83 |  |  |  | 0 | vertical barrier: MOO sell at the next o |
| LITE | SELL at open | 0 |  | 941.65 |  |  |  | 0 | vertical barrier: MOO sell at the next o |
| RKLB | SELL at open | 0 |  | 73.95 |  |  |  | 0 | vertical barrier: MOO sell at the next o |
| SMCI | SELL at open | 0 |  | 43.26 |  |  |  | 0 | vertical barrier: MOO sell at the next o |
| TER | SELL at open | 0 |  | 398.38 |  |  |  | 0 | vertical barrier: MOO sell at the next o |
| WDC | SELL at open | 0 |  | 456.81 |  |  |  | 0 | vertical barrier: MOO sell at the next o |

_Vertical exit: MOO 40 sessions after entry. Trailing stop: each night raise a long's stop to the high since fill minus trail %, never below the fixed stop. HOLD rows price the most binding lot's levels off the last close. Research tooling, not financial advice._