# Daily flood-label experiment (exploratory)

Generated 2026-10-28T03:01:26+00:00 by `scripts/daily_flood_experiment.py`. City-level flood day from BPBD incident dates; ERA5 daily rainfall (Open-Meteo archive) for north/south Jakarta and the upper Ciliwung.

Flood days (>= 1 kelurahan) per year: 2020: 110, 2021: 84, 2022: 135, 2023: 71, 2024: 144, 2025: 147

| Flood day | Split | Model | Test days / flood days | Prevalence | ROC-AUC | PR-AUC | Precision @ recall 0.8 | Precision @ recall 0.5 | 3-day rain alone ROC-AUC |
|---|---|---|---|---|---|---|---|---|---|
| >= 1 kelurahan | train 2020–2021, test 2022 (complete dates) | logistic | 365 / 135 | 0.37 | 0.577 | 0.443 | 0.408 | 0.433 | 0.617 |
| >= 1 kelurahan | train 2020–2021, test 2022 (complete dates) | xgboost | 365 / 135 | 0.37 | 0.568 | 0.406 | 0.396 | 0.455 | 0.617 |
| >= 1 kelurahan | train 2020–2022, test 2023–2025 (partial dates) | logistic | 1096 / 362 | 0.33 | 0.682 | 0.504 | 0.422 | 0.488 | 0.674 |
| >= 1 kelurahan | train 2020–2022, test 2023–2025 (partial dates) | xgboost | 1096 / 362 | 0.33 | 0.66 | 0.464 | 0.406 | 0.457 | 0.674 |
| >= 5 kelurahan | train 2020–2021, test 2022 (complete dates) | logistic | 365 / 51 | 0.14 | 0.661 | 0.232 | 0.183 | 0.216 | 0.66 |
| >= 5 kelurahan | train 2020–2021, test 2022 (complete dates) | xgboost | 365 / 51 | 0.14 | 0.635 | 0.192 | 0.189 | 0.208 | 0.66 |
| >= 5 kelurahan | train 2020–2022, test 2023–2025 (partial dates) | logistic | 1096 / 91 | 0.083 | 0.78 | 0.25 | 0.153 | 0.201 | 0.769 |
| >= 5 kelurahan | train 2020–2022, test 2023–2025 (partial dates) | xgboost | 1096 / 91 | 0.083 | 0.746 | 0.19 | 0.139 | 0.182 | 0.769 |

- 2023–2025 dates are readable for only 40–74 % of BPBD rows, so some flood days there are labelled dry and precision is a lower bound.
- ERA5 is a reanalysis (about 25 km grid), not a rain gauge; local downpours are smoothed.
