# Precision experiments

Generated 2026-10-28T02:59:48+00:00 by `scripts/precision_experiments.py`. The served bundle is not touched.

## Labels: dataset vs BPBD records (kecamatan-months flagged as flood)

| Year | Rows | Dataset label | BPBD records | Both |
|---|---|---|---|---|
| 2020 | 589 | 117 | 267 | 116 |
| 2021 | 595 | 78 | 147 | 78 |
| 2022 | 580 | 54 | 213 | 53 |
| 2023 | 577 | 11 | 113 | 8 |
| 2024 | 587 | 22 | 155 | 21 |

## by_year/dataset model, scored on own labels

Split: by_year (train<2023, val 2023–2023, test>=2024); calibration sigmoid; validation positives 11. Test 587 rows, 22 floods (prevalence 0.037). ROC-AUC 0.826 [0.745–0.889], PR-AUC 0.124 [0.078–0.192].

| Danger threshold rule (chosen on validation) | Threshold | Recall | Precision | F1 | Alarms | False alarms | Missed |
|---|---|---|---|---|---|---|---|
| current (recall-first, precision >= 0.30) | 0.347 | 0.864 | 0.128 | 0.222 | 149 | 130 | 3 |
| best F1 on validation | 0.5336 | 0.045 | 0.026 | 0.033 | 38 | 37 | 21 |
| best F0.5 on validation (precision-weighted) | 0.5336 | 0.045 | 0.026 | 0.033 | 38 | 37 | 21 |

## by_year/dataset model, scored on bpbd labels

Split: by_year (train<2023, val 2023–2023, test>=2024); calibration sigmoid; validation positives 11. Test 587 rows, 155 floods (prevalence 0.264). ROC-AUC 0.76 [0.715–0.802], PR-AUC 0.555 [0.48–0.638].

| Danger threshold rule (chosen on validation) | Threshold | Recall | Precision | F1 | Alarms | False alarms | Missed |
|---|---|---|---|---|---|---|---|
| current (recall-first, precision >= 0.30) | 0.347 | 0.51 | 0.53 | 0.52 | 149 | 70 | 76 |
| best F1 on validation | 0.5336 | 0.174 | 0.711 | 0.28 | 38 | 11 | 128 |
| best F0.5 on validation (precision-weighted) | 0.5336 | 0.174 | 0.711 | 0.28 | 38 | 11 | 128 |

## by_year/bpbd model, scored on own labels

Split: by_year (train<2023, val 2023–2023, test>=2024); calibration isotonic; validation positives 113. Test 587 rows, 155 floods (prevalence 0.264). ROC-AUC 0.76 [0.715–0.8], PR-AUC 0.501 [0.426–0.589].

| Danger threshold rule (chosen on validation) | Threshold | Recall | Precision | F1 | Alarms | False alarms | Missed |
|---|---|---|---|---|---|---|---|
| current (recall-first, precision >= 0.30) | 0.2283 | 0.948 | 0.336 | 0.497 | 437 | 290 | 8 |
| best F1 on validation | 0.3699 | 0.729 | 0.479 | 0.578 | 236 | 123 | 42 |
| best F0.5 on validation (precision-weighted) | 0.42 | 0.548 | 0.486 | 0.515 | 175 | 90 | 70 |
| highest recall with precision >= 0.50 on validation | 0.3404 | 0.748 | 0.411 | 0.531 | 282 | 166 | 39 |

## by_year/bpbd model, scored on dataset labels

Split: by_year (train<2023, val 2023–2023, test>=2024); calibration isotonic; validation positives 113. Test 587 rows, 22 floods (prevalence 0.037). ROC-AUC 0.754 [0.678–0.824], PR-AUC 0.081 [0.051–0.128].

| Danger threshold rule (chosen on validation) | Threshold | Recall | Precision | F1 | Alarms | False alarms | Missed |
|---|---|---|---|---|---|---|---|
| current (recall-first, precision >= 0.30) | 0.2283 | 0.955 | 0.048 | 0.092 | 437 | 416 | 1 |
| best F1 on validation | 0.3699 | 0.955 | 0.089 | 0.163 | 236 | 215 | 1 |
| best F0.5 on validation (precision-weighted) | 0.42 | 0.636 | 0.08 | 0.142 | 175 | 161 | 8 |
| highest recall with precision >= 0.50 on validation | 0.3404 | 0.955 | 0.074 | 0.138 | 282 | 261 | 1 |

## random/dataset model, scored on own labels

Split: random_stratified_68_12_20 (fallback: chronological_68_12_20 had no positives); calibration sigmoid; validation positives 34. Test 586 rows, 56 floods (prevalence 0.096). ROC-AUC 0.899 [0.858–0.938], PR-AUC 0.525 [0.396–0.65].

| Danger threshold rule (chosen on validation) | Threshold | Recall | Precision | F1 | Alarms | False alarms | Missed |
|---|---|---|---|---|---|---|---|
| current (recall-first, precision >= 0.30) | 0.1255 | 0.875 | 0.282 | 0.426 | 174 | 125 | 7 |
| best F1 on validation | 0.7151 | 0.375 | 0.512 | 0.433 | 41 | 20 | 35 |
| best F0.5 on validation (precision-weighted) | 0.7151 | 0.375 | 0.512 | 0.433 | 41 | 20 | 35 |
| highest recall with precision >= 0.50 on validation | 0.4252 | 0.661 | 0.435 | 0.525 | 85 | 48 | 19 |

## random/bpbd model, scored on own labels

Split: chronological_68_12_20; calibration isotonic; validation positives 43. Test 586 rows, 154 floods (prevalence 0.263). ROC-AUC 0.793 [0.751–0.83], PR-AUC 0.563 [0.484–0.647].

| Danger threshold rule (chosen on validation) | Threshold | Recall | Precision | F1 | Alarms | False alarms | Missed |
|---|---|---|---|---|---|---|---|
| current (recall-first, precision >= 0.30) | 0.2035 | 0.903 | 0.355 | 0.51 | 391 | 252 | 15 |
| best F1 on validation | 0.2465 | 0.857 | 0.394 | 0.54 | 335 | 203 | 22 |
| best F0.5 on validation (precision-weighted) | 0.4041 | 0.597 | 0.586 | 0.592 | 157 | 65 | 62 |
| highest recall with precision >= 0.50 on validation | 0.3985 | 0.617 | 0.565 | 0.59 | 168 | 73 | 59 |

- Recall/precision at a threshold chosen on one validation year move a lot between runs; ROC-AUC and PR-AUC do not depend on the threshold.
- The BPBD label marks a kecamatan-month as flooded when any RW in it reported a flood that month.
