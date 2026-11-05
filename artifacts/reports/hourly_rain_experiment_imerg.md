# Hourly vs daily rain, flood days per kecamatan (imerg)

Generated 2026-11-05T02:29:34+00:00 by `scripts/hourly_rain_experiment.py --source imerg`. Rain: GPM IMERG Final half-hourly (satellite + gauges, 0.1°). Rows: 88,200 kecamatan-days, 2,561 with a BPBD flood.

Flood kecamatan-days per year: 2020: 704, 2021: 323, 2022: 544, 2023: 213, 2024: 424, 2025: 353

Record storm check, 1 Jan 2020: wettest kecamatan 101.1 mm that day (wettest hour 17.9 mm); BMKG Halim measured 377 mm.

| Split | Model | Features | Test rows / floods | ROC-AUC | PR-AUC | Precision @ recall 0.5 | Hourly − daily, 95 % CI |
|---|---|---|---|---|---|---|---|
| train 2020–2021, test 2022 (complete dates) | logistic | daily | 15,330 / 544 | 0.729 | 0.108 | 0.08 |  |
| train 2020–2021, test 2022 (complete dates) | logistic | hourly | 15,330 / 544 | 0.714 | 0.1 | 0.077 | ROC [-0.026, -0.002], PR [-0.018, 0.01] |
| train 2020–2021, test 2022 (complete dates) | xgboost | daily | 15,330 / 544 | 0.754 | 0.104 | 0.092 |  |
| train 2020–2021, test 2022 (complete dates) | xgboost | hourly | 15,330 / 544 | 0.758 | 0.096 | 0.087 | ROC [-0.015, 0.023], PR [-0.023, 0.011] |
| train 2020–2021, test 2022 (complete dates) | rain alone | day total vs wettest 3 h | | 0.597 vs 0.59 | | | |
| train 2020–2022, test 2023–Sep 2025 (partial dates) | logistic | daily | 42,168 / 990 | 0.837 | 0.168 | 0.122 |  |
| train 2020–2022, test 2023–Sep 2025 (partial dates) | logistic | hourly | 42,168 / 990 | 0.839 | 0.177 | 0.128 | ROC [-0.004, 0.006], PR [-0.009, 0.036] |
| train 2020–2022, test 2023–Sep 2025 (partial dates) | xgboost | daily | 42,168 / 990 | 0.827 | 0.177 | 0.123 |  |
| train 2020–2022, test 2023–Sep 2025 (partial dates) | xgboost | hourly | 42,168 / 990 | 0.825 | 0.176 | 0.125 | ROC [-0.008, 0.004], PR [-0.02, 0.022] |
| train 2020–2022, test 2023–Sep 2025 (partial dates) | rain alone | day total vs wettest 3 h | | 0.743 vs 0.747 | | | |

- 2023–2025 BPBD dates are only partly readable, so those labels miss floods; precision there is a lower bound.
- Each kecamatan takes the rain of the cell that holds its centroid; upstream = Katulampa (Bogor) and Depok cells.
