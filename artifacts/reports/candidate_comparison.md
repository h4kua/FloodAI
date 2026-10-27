# Candidate vs current pipeline (by year: train 2020–2022, validate 2023, test 2024)

Generated 2026-10-27T06:18:49+00:00 by `scripts/train_candidate.py` (1000 bootstrap resamples, 95 % CIs). Test year 2024: 587 rows, 22 floods.

| Pipeline | Features | Calibration | ROC-AUC | PR-AUC | Recall | Precision | Brier | ECE | Threshold |
|---|---|---|---|---|---|---|---|---|---|
| Current | 17 | isotonic (5-fold CV on train) | 0.812 [0.741–0.869] | 0.104 [0.064–0.162] | 0.864 [0.720–1.000] | 0.124 [0.074–0.183] | 0.095 [0.086–0.104] | 0.192 | 0.425 |
| Candidate | 13 | sigmoid (validation fold (latest year)) | 0.733 [0.681–0.787] | 0.085 [0.051–0.133] | 0.000 [0.000–0.000] | 0.000 [0.000–0.000] | 0.037 [0.022–0.052] | 0.025 | 0.081 |

- Paired gain (candidate minus current, same 2024 rows): ROC-AUC -0.079 [-0.131 to -0.026], PR-AUC -0.020 [-0.044 to -0.001].
- Recall and precision are at each pipeline's own threshold, chosen on 2023 (11 floods), so they move a lot between runs; ROC-AUC, PR-AUC, Brier and ECE do not depend on it.
- Candidate bundle: `models/candidates/realtime_native_core_latestcal` (not served). Native-format parity with the trained model: max probability difference =2.00e-07.
- Data: bootstrap-proxy kecamatan-month rows; no observed field labels.
