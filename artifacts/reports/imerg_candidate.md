# IMERG candidate vs served model

Generated 2026-11-05T05:40:46+00:00 by `scripts/train_imerg_candidate.py`. The served bundle is not touched. Split: train 2020–2022, validate 2023, test 2024.

Rain input: dataset `max_rainfall` vs IMERG wettest day, correlation 0.392 (medians 49.1 vs 46.2 mm); `avg_rainfall` vs IMERG mean daily rain, correlation 0.859 (medians 23.6 vs 7.9 mm).

| Model | Labels | Test rows / floods | ROC-AUC [95 %] | PR-AUC [95 %] | Danger rule: recall / precision / alarms |
|---|---|---|---|---|---|
| served | dataset | 587 / 22 | 0.826 [0.745–0.889] | 0.124 [0.078–0.192] | 0.864 / 0.128 / 149 |
| served | bpbd | 587 / 155 | 0.76 [0.715–0.802] | 0.555 [0.48–0.638] | 0.51 / 0.53 / 149 |
| imerg_all | dataset | 587 / 22 | 0.711 [0.624–0.791] | 0.084 [0.047–0.167] | 0.909 / 0.056 / 360 |
| imerg_all | bpbd | 587 / 155 | 0.728 [0.683–0.772] | 0.494 [0.413–0.578] | 0.794 / 0.342 / 360 |
| imerg_no_proxy | dataset | 587 / 22 | 0.715 [0.608–0.808] | 0.077 [0.046–0.136] | 0.636 / 0.077 / 182 |
| imerg_no_proxy | bpbd | 587 / 155 | 0.787 [0.745–0.826] | 0.612 [0.533–0.682] | 0.587 / 0.5 / 182 |

## Candidate minus served, same 2024 rows (paired bootstrap, 95 %)

| Candidate | Labels | ROC-AUC difference | PR-AUC difference |
|---|---|---|---|
| imerg_all | dataset | [-0.185, -0.049] | [-0.088, 0.014] |
| imerg_all | bpbd | [-0.067, 0.004] | [-0.127, 0.016] |
| imerg_no_proxy | dataset | [-0.223, -0.01] | [-0.098, 0.009] |
| imerg_no_proxy | bpbd | [-0.022, 0.079] | [-0.031, 0.146] |

- The Danger rule is the served one (recall first, precision >= 0.30 on the validation year).
- The BPBD label marks a kecamatan-month as flooded when any RW in it reported a flood that month.
- IMERG Final lags about 3.5 months, so serving this candidate would need IMERG Early rain.
