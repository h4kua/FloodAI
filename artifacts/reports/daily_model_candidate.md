# Daily model: calibration, warning levels and a candidate bundle

Generated 2026-11-12T01:07:52+00:00 by `scripts/daily_model_candidate.py` on cuda. Nothing here is served.

Out-of-sample XGBoost F4 probabilities (each year from a model trained on earlier years), calibrated with an isotonic map fitted on the earlier years only.

| Year | Floods | ROC-AUC | ECE raw | ECE calibrated | ECE calibrated (equal-count bins) | Brier raw | Brier calibrated | Mean p calibrated | Prevalence |
|---|---|---|---|---|---|---|---|---|---|
| 2017 | 239 | 0.859 | 0.1175 | 0.016 | 0.016 | 0.0617 | 0.0149 | 0.0316 | 0.0156 |
| 2018 | 151 | 0.884 | 0.1056 | 0.0089 | 0.0088 | 0.0507 | 0.0097 | 0.0187 | 0.0098 |
| 2019 | 145 | 0.918 | 0.1151 | 0.0082 | 0.0082 | 0.0588 | 0.0091 | 0.0176 | 0.0095 |
| 2020 | 704 | 0.813 | 0.1744 | 0.0186 | 0.0129 | 0.1216 | 0.0432 | 0.0367 | 0.0458 |
| 2021 | 323 | 0.865 | 0.2071 | 0.0143 | 0.0121 | 0.1061 | 0.0185 | 0.0332 | 0.0211 |
| 2022 | 544 | 0.784 | 0.1778 | 0.0106 | 0.0118 | 0.1001 | 0.0332 | 0.0255 | 0.0355 |
| 2023 | 213 | 0.919 | 0.1672 | 0.0117 | 0.0115 | 0.0859 | 0.0126 | 0.0254 | 0.0139 |
| 2024 | 424 | 0.822 | 0.223 | 0.0051 | 0.0055 | 0.128 | 0.0251 | 0.0326 | 0.0276 |
| 2025 | 353 | 0.871 | 0.2551 | 0.0078 | 0.0068 | 0.1427 | 0.027 | 0.0364 | 0.0308 |

Pooled 2017–2025: ECE raw 0.169 → calibrated 0.0055 (equal-count bins 0.169 → 0.0058); Brier 0.0937 → 0.0213; prevalence 0.0231.

Reliability, calibrated, pooled (equal-count bins):

| Predicted p range | Rows | Mean predicted | Observed flood rate |
|---|---|---|---|
| 0.0–0.0021 | 13379 | 0.0004 | 0.0001 |
| 0.0021–0.0034 | 11052 | 0.0029 | 0.0013 |
| 0.0034–0.0053 | 15621 | 0.0038 | 0.0024 |
| 0.0053–0.0081 | 13211 | 0.0066 | 0.0045 |
| 0.0081–0.0098 | 13008 | 0.009 | 0.0039 |
| 0.0098–0.0181 | 13648 | 0.0134 | 0.011 |
| 0.0181–0.0278 | 13971 | 0.0236 | 0.0257 |
| 0.0278–0.039 | 13288 | 0.0326 | 0.0228 |
| 0.039–0.0757 | 13436 | 0.0489 | 0.0395 |
| 0.0757–1.0 | 13576 | 0.1406 | 0.117 |

Warning levels by alarm budget (chosen on 2016–2024, scored on Jan–Sep 2025):

| Level | Budget (alarm days per kecamatan-month) | Threshold | 2025 alarm days per kecamatan-month | 2025 recall | 2025 precision |
|---|---|---|---|---|---|
| Waspada | 4 | 0.0513 | 5.71 | 0.686 | 0.112 |
| Siaga | 2 | 0.0922 | 2.94 | 0.513 | 0.163 |
| Bahaya | 1 | 0.1408 | 1.71 | 0.365 | 0.2 |

Candidate bundle: `models/candidates/daily_f4/` (model.json, isotonic.json, model_card.json).
