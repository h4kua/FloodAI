# Hourly vs daily rain, flood days per kecamatan (openmeteo)

Generated 2026-11-05T02:14:14+00:00 by `scripts/hourly_rain_experiment.py --source openmeteo`. Rain: ERA5 hourly reanalysis via Open-Meteo (about 25 km). Rows: 88,200 kecamatan-days, 2,561 with a BPBD flood.

Flood kecamatan-days per year: 2020: 704, 2021: 323, 2022: 544, 2023: 213, 2024: 424, 2025: 353

Record storm check, 1 Jan 2020: wettest kecamatan 31.3 mm that day (wettest hour 2.9 mm); BMKG Halim measured 377 mm.

| Split | Model | Features | Test rows / floods | ROC-AUC | PR-AUC | Precision @ recall 0.5 | Hourly − daily, 95 % CI |
|---|---|---|---|---|---|---|---|
| train 2020–2021, test 2022 (complete dates) | logistic | daily | 15,330 / 544 | 0.667 | 0.07 | 0.057 |  |
| train 2020–2021, test 2022 (complete dates) | logistic | hourly | 15,330 / 544 | 0.68 | 0.068 | 0.061 | ROC [-0.001, 0.028], PR [-0.015, 0.007] |
| train 2020–2021, test 2022 (complete dates) | xgboost | daily | 15,330 / 544 | 0.744 | 0.099 | 0.078 |  |
| train 2020–2021, test 2022 (complete dates) | xgboost | hourly | 15,330 / 544 | 0.755 | 0.099 | 0.086 | ROC [-0.008, 0.029], PR [-0.02, 0.016] |
| train 2020–2021, test 2022 (complete dates) | rain alone | day total vs wettest 3 h | | 0.591 vs 0.605 | | | |
| train 2020–2022, test 2023–Sep 2025 (partial dates) | logistic | daily | 42,168 / 990 | 0.798 | 0.094 | 0.085 |  |
| train 2020–2022, test 2023–Sep 2025 (partial dates) | logistic | hourly | 42,168 / 990 | 0.795 | 0.103 | 0.083 | ROC [-0.01, 0.004], PR [-0.005, 0.026] |
| train 2020–2022, test 2023–Sep 2025 (partial dates) | xgboost | daily | 42,168 / 990 | 0.798 | 0.087 | 0.082 |  |
| train 2020–2022, test 2023–Sep 2025 (partial dates) | xgboost | hourly | 42,168 / 990 | 0.789 | 0.078 | 0.076 | ROC [-0.017, -0.0], PR [-0.026, 0.001] |
| train 2020–2022, test 2023–Sep 2025 (partial dates) | rain alone | day total vs wettest 3 h | | 0.701 vs 0.698 | | | |

- 2023–2025 BPBD dates are only partly readable, so those labels miss floods; precision there is a lower bound.
- Each kecamatan takes the rain of the cell that holds its centroid; upstream = Katulampa (Bogor) and Depok cells.
