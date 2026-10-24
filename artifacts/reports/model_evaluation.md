# Realtime-native model evaluation

Generated 2026-10-24T12:28:21+00:00 by `scripts/evaluate_model.py` (1000 bootstrap resamples, 95 % percentile CIs).

| View | Test rows / positives | ROC-AUC | PR-AUC | PR-AUC no-skill | Recall | Precision | Brier | ECE | Threshold |
|---|---|---|---|---|---|---|---|---|---|
| Deployed bundle (random split) | 586 / 56 | 0.904 [0.866–0.940] | 0.528 [0.397–0.669] | 0.096 | 0.893 [0.810–0.965] | 0.263 [0.199–0.327] | 0.074 [0.059–0.088] | 0.062 | 0.103 |
| Pipeline re-run, random split | 586 / 56 | 0.904 [0.866–0.940] | 0.528 [0.397–0.669] | 0.096 | 0.893 [0.810–0.965] | 0.263 [0.199–0.327] | 0.074 [0.059–0.088] | 0.062 | 0.103 |
| Pipeline re-run, by year (test 2024) | 587 / 22 | 0.812 [0.741–0.869] | 0.104 [0.064–0.162] | 0.037 | 0.864 [0.720–1.000] | 0.124 [0.074–0.183] | 0.095 [0.086–0.104] | 0.192 | 0.425 |

- Data: bootstrap-proxy kecamatan-month rows (2020–2024); several features are proxies (see context.md, *Model & evaluation*). No observed field labels exist yet.
- The by-year view trains on 2020–2022, picks the threshold on 2023 and tests on 2024 (few positives, so its intervals are wide).
- PR-AUC no-skill baseline = share of flood rows in the test set.
