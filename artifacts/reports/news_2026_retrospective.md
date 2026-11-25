# Daily model on 2026 news flood days (out of time)

Replay of the served daily kecamatan model (rain, place, season; no water inputs) on every day of 2026 against the Jakarta flood days found in detik.com reports. Positives only: a day without a report is *not reported*, not *no flood*, so ranking is meaningful and precision is not.

- Days scored 328, news flood days 34, large flood days (>= 10 kecamatan named) 11. Rain lag used: {1: 328}.
- City ROC-AUC, flood day vs other days: **0.844** (95 % CI [0.792, 0.889]); 7-day rain rule alone 0.821; difference model - rain CI [-0.017, 0.064].
- Large flood days only: model 0.892, 7-day rain 0.888.
- At the served Waspada threshold the model raises 77 days (24%); it catches 62% of the flood days and 82% of the large ones. The 7-day rain rule with the same number of alarm days catches 62% / 82%.
- Kecamatan level: AUC 0.874 over all kecamatan-days; on flood days the reported kecamatan sit at the 0.704 mean percentile of the 42.

## By month

| Month | Days | Alarm days | News flood days | Flood days with alarm |
|---|---|---|---|---|
| 2026-01 | 31 | 26 | 15 | 11 |
| 2026-02 | 28 | 26 | 5 | 5 |
| 2026-03 | 31 | 3 | 5 | 1 |
| 2026-04 | 30 | 3 | 3 | 0 |
| 2026-05 | 31 | 7 | 6 | 4 |
| 2026-06 | 30 | 2 | 0 | 0 |
| 2026-07 | 31 | 1 | 0 | 0 |
| 2026-08 | 31 | 0 | 0 | 0 |
| 2026-09 | 30 | 1 | 0 | 0 |
| 2026-10 | 31 | 7 | 0 | 0 |
| 2026-11 | 24 | 1 | 0 | 0 |

## Large flood days

| Date | Kecamatan named | Chance | Level | 7-day rain (mm, city max) | Top kecamatan |
|---|---|---|---|---|---|
| 2026-01-12 | 26 | 20% | PRE_ALERT | 92.1 | Jatinegara |
| 2026-01-13 | 11 | 20% | PRE_ALERT | 121.7 | Penjaringan |
| 2026-01-18 | 26 | 21% | PRE_ALERT | 144.8 | Penjaringan |
| 2026-01-22 | 28 | 14% | PRE_ALERT | 140.3 | Cengkareng |
| 2026-01-23 | 25 | 21% | PRE_ALERT | 157.1 | Jatinegara |
| 2026-01-24 | 15 | 14% | PRE_ALERT | 162.6 | Jatinegara |
| 2026-01-29 | 21 | 9% | SAFE | 72.5 | Jatinegara |
| 2026-01-30 | 14 | 14% | PRE_ALERT | 71.1 | Jatinegara |
| 2026-02-20 | 17 | 24% | PRE_ALERT | 161.5 | Jatinegara |
| 2026-03-08 | 22 | 9% | SAFE | 90.6 | Jatinegara |
| 2026-05-05 | 14 | 21% | PRE_ALERT | 133.7 | Jatinegara |

## Flood days with no alarm (misses)

| Date | Kecamatan named | Reports | Chance | 7-day rain |
|---|---|---|---|---|
| 2026-03-08 | 22 | 11 | 9% | 90.6 |
| 2026-01-29 | 21 | 13 | 9% | 72.5 |
| 2026-03-09 | 9 | 3 | 9% | 102.4 |
| 2026-05-01 | 9 | 4 | 9% | 47.1 |
| 2026-03-22 | 7 | 4 | 6% | 69.3 |
| 2026-01-25 | 6 | 4 | 9% | 132.6 |
| 2026-04-17 | 6 | 2 | 9% | 62.1 |
| 2026-04-04 | 5 | 2 | 9% | 77.0 |
| 2026-04-20 | 5 | 3 | 8% | 46.8 |
| 2026-05-19 | 4 | 2 | 8% | 34.2 |
| 2026-01-26 | 2 | 1 | 9% | 80.1 |
| 2026-01-27 | 1 | 1 | 9% | 83.6 |
| 2026-03-11 | 1 | 1 | 9% | 83.0 |
