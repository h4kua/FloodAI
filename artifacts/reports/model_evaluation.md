# Realtime-native model evaluation

Generated 2026-10-28T02:32:31+00:00 by `scripts/evaluate_model.py` (1000 bootstrap resamples, 95 % percentile CIs).

| View | Test rows / positives | ROC-AUC | PR-AUC | PR-AUC no-skill | Recall | Precision | Brier | ECE | Threshold |
|---|---|---|---|---|---|---|---|---|---|
| Deployed bundle (random split) | 586 / 56 | 0.899 [0.858–0.938] | 0.525 [0.393–0.665] | 0.096 | 0.875 [0.781–0.957] | 0.282 [0.212–0.349] | 0.074 [0.059–0.089] | 0.062 | 0.126 |
| Pipeline re-run, random split | 586 / 56 | 0.899 [0.858–0.938] | 0.525 [0.393–0.665] | 0.096 | 0.875 [0.781–0.957] | 0.282 [0.212–0.349] | 0.074 [0.059–0.089] | 0.062 | 0.126 |
| Pipeline re-run, by year (test 2024) | 587 / 22 | 0.826 [0.745–0.889] | 0.124 [0.075–0.199] | 0.037 | 0.864 [0.720–1.000] | 0.128 [0.077–0.188] | 0.078 [0.070–0.088] | 0.169 | 0.347 |

- Data: bootstrap-proxy kecamatan-month rows (2020–2024); several features are proxies (see context.md, *Model & evaluation*). No observed field labels exist yet.
- The by-year view trains on 2020–2022, picks the threshold on 2023 and tests on 2024 (few positives, so its intervals are wide).
- PR-AUC no-skill baseline = share of flood rows in the test set.
