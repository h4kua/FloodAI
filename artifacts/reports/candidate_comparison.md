# Candidate vs current pipeline (by year: train 2020–2022, validate 2023, test 2024)

Generated 2026-10-28T02:33:12+00:00 by `scripts/train_candidate.py` (1000 bootstrap resamples, 95 % CIs). Test year 2024: 587 rows, 22 floods.

| Pipeline | Features | Calibration | ROC-AUC | PR-AUC | Recall | Precision | Brier | ECE | Threshold |
|---|---|---|---|---|---|---|---|---|---|
| Current | 17 | sigmoid (5-fold CV on train) | 0.826 [0.745–0.889] | 0.124 [0.075–0.199] | 0.864 [0.720–1.000] | 0.128 [0.077–0.188] | 0.078 [0.070–0.088] | 0.169 | 0.347 |
| Candidate | 13 | sigmoid (validation fold (latest year)) | 0.796 [0.720–0.871] | 0.113 [0.064–0.185] | 0.318 [0.130–0.543] | 0.119 [0.043–0.208] | 0.035 [0.021–0.050] | 0.023 | 0.076 |

- Paired gain (candidate minus current, same 2024 rows): ROC-AUC -0.029 [-0.071 to +0.013], PR-AUC -0.013 [-0.050 to +0.023].
- Recall and precision are at each pipeline's own threshold, chosen on 2023 (11 floods), so they move a lot between runs; ROC-AUC, PR-AUC, Brier and ECE do not depend on it.
- Candidate bundle: `models/candidates/realtime_native_core_latestcal` (not served). Native-format parity with the trained model: max probability difference =7.57e-07.
- Data: bootstrap-proxy kecamatan-month rows; no observed field labels.
