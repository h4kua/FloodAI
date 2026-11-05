# IMERG vs ERA5 rain, flood days per kecamatan

Generated 2026-11-05T02:31:54+00:00 by `scripts/rain_source_comparison.py`. Same 88,200 kecamatan-days, same labels and model, daily feature set; only the rain source differs.

| Split | Model | ROC-AUC ERA5 → IMERG | PR-AUC ERA5 → IMERG | IMERG − ERA5, 95 % CI |
|---|---|---|---|---|
| train 2020–2021, test 2022 (complete dates) | logistic | 0.667 → 0.729 | 0.07 → 0.108 | ROC [0.021, 0.1], PR [0.013, 0.067] |
| train 2020–2021, test 2022 (complete dates) | xgboost | 0.744 → 0.754 | 0.099 → 0.104 | ROC [-0.036, 0.055], PR [-0.031, 0.036] |
| train 2020–2022, test 2023–Sep 2025 (partial dates) | logistic | 0.798 → 0.837 | 0.094 → 0.168 | ROC [0.019, 0.062], PR [0.034, 0.107] |
| train 2020–2022, test 2023–Sep 2025 (partial dates) | xgboost | 0.798 → 0.827 | 0.087 → 0.177 | ROC [0.01, 0.051], PR [0.041, 0.138] |
