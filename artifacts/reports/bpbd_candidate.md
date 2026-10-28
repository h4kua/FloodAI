# BPBD-label candidate (not served)

Generated 2026-10-28T03:09:58+00:00 by `scripts/train_bpbd_candidate.py`. Bundle: `models/candidates/realtime_native_bpbd_labels/`.

Split chronological_68_12_20 (train/val/test rows [1990, 352, 586]); calibration isotonic. Test: 154 BPBD floods (prevalence 0.263), ROC-AUC 0.793, PR-AUC 0.563, Brier 0.157, ECE 0.085.

| Level | Served threshold | Candidate threshold | Candidate validation recall / precision |
|---|---|---|---|
| Waspada | 0.07 | 0.1861 | 0.953 / 0.279 |
| Siaga | 0.07 | 0.2035 | 0.93 / 0.303 |
| Bahaya | 0.1255 | 0.2465 | 0.86 / 0.389 |

## Model-layer level, 2023 kecamatan-months (BPBD flood rate 0.196)

| Level | Served: share of rows | Served: BPBD flood rate | Candidate: share of rows | Candidate: BPBD flood rate |
|---|---|---|---|---|
| SAFE | 0.842 | 0.126 | 0.456 | 0.008 |
| PRE_ALERT | 0.0 | None | 0.04 | 0.043 |
| WARNING | 0.059 | 0.382 | 0.12 | 0.072 |
| DANGER | 0.099 | 0.684 | 0.385 | 0.473 |

## Model-layer level, 2024 kecamatan-months (BPBD flood rate 0.264)

| Level | Served: share of rows | Served: BPBD flood rate | Candidate: share of rows | Candidate: BPBD flood rate |
|---|---|---|---|---|
| SAFE | 0.813 | 0.17 | 0.305 | 0.067 |
| PRE_ALERT | 0.0 | None | 0.027 | 0.188 |
| WARNING | 0.048 | 0.429 | 0.095 | 0.125 |
| DANGER | 0.14 | 0.756 | 0.572 | 0.396 |

Live snapshot (city features): served p=0.0009 → SAFE; candidate p=0.1414 → SAFE.

- The served bundle was trained on a random split that includes most 2023–2024 rows, so its level shares there are in-sample; the candidate's 2024 rows are its test set.
- Only the model layer is shown; the decision engine's rule layers can raise or cap the level.
- Monthly training rows differ from 15-minute live snapshots, so live level shares will differ.
