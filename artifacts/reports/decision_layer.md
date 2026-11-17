# Learned decision layer vs the current rules

Generated 2026-11-17T12:35:32+00:00 by `scripts/train_decision_layer.py` on cuda (1000 day resamples).

Features: p, w_max_now, w_frac1_now, w_frac2_now, w_upstream_now, w_manggarai_now, w_max_d1, w_frac1_d1, w_frac2_d1, w_upstream_d1, w_manggarai_d1. Current = river rules (Siaga 3/2/1 -> Waspada/Siaga/Bahaya) + the daily model's Waspada. Learned: a flood score from one of three learners (depth-3 tree; logistic regression; XGBoost depth 2 with every feature monotone increasing), thresholds per level set on the training years (leave-one-year-out scores) at the precision the current level has there, so at equal precision the one catching more floods is better. A river post at Siaga 1 stays Bahaya. Test years 2019, 2020, 2021, 2025, each trained on earlier snapshots only. 'Equal volume' re-cuts the learned score on the test rows to the current alarm shares (a ranking check, not deployable).

Served: **xgb_monotone** (volume-matched thresholds), thresholds {'lag 1': {'PRE_ALERT': 0.21118, 'WARNING': 0.6117, 'DANGER': 0.76178}, 'lag 2': {'PRE_ALERT': 0.22189, 'WARNING': 0.61886, 'DANGER': 0.76152}, 'lag 3': {'PRE_ALERT': 0.21843, 'WARNING': 0.63821, 'DANGER': 0.77641}}.

## lag 1 · 3090 test snapshots on 1062 days (flood days 0.221, large 0.076)

### tree · precision-matched

Thresholds by test year: {'2019': {'Waspada': None, 'Siaga': None, 'Bahaya': None}, '2020': {'Waspada': None, 'Siaga': None, 'Bahaya': None}, '2021': {'Waspada': 0.1882, 'Siaga': None, 'Bahaya': None}, '2025': {'Waspada': 0.3913, 'Siaga': 0.5, 'Bahaya': None}}

**any flood**: ROC-AUC current 0.694 [0.663–0.723], learned 0.749 [0.71–0.784], difference [0.024, 0.091].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.558 / 0.458 | 0.118 / 0.189 / 0.353 | [-0.432, -0.296], [-0.181, -0.015] | 0.66 / 0.417 | [0.035, 0.172], [-0.082, 0.001] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.017 / 0.059 / 0.741 | [-0.096, -0.048], [-0.098, 0.125] | 0.138 / 0.528 | [-0.036, 0.056], [-0.334, -0.068] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.015 / 0.051 / 0.761 | [0.0, 0.0], [0.0, 0.0] | 0.051 / 0.686 | [-0.031, 0.037], [-0.335, 0.213] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.752 [0.7–0.802], learned 0.719 [0.668–0.761], difference [-0.077, 0.013].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.706 / 0.2 | 0.118 / 0.136 / 0.088 | [-0.675, -0.466], [-0.162, -0.062] | 0.766 / 0.166 | [-0.053, 0.176], [-0.061, -0.006] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.017 / 0.094 / 0.407 | [-0.17, -0.062], [-0.105, 0.127] | 0.106 / 0.14 | [-0.173, -0.025], [-0.36, -0.144] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.015 / 0.085 / 0.435 | [0.0, 0.0], [0.0, 0.0] | 0.043 / 0.196 | [-0.091, 0.004], [-0.43, -0.013] |

Snapshots below the current level: 0.206 (with a river post at Siaga 2+: 0.024).

### logistic · precision-matched

Thresholds by test year: {'2019': {'Waspada': None, 'Siaga': None, 'Bahaya': None}, '2020': {'Waspada': 0.1258, 'Siaga': 0.827, 'Bahaya': None}, '2021': {'Waspada': 0.2132, 'Siaga': 0.8677, 'Bahaya': 0.8961}, '2025': {'Waspada': 0.1859, 'Siaga': 0.8404, 'Bahaya': 0.9079}}

**any flood**: ROC-AUC current 0.694 [0.663–0.723], learned 0.749 [0.706–0.787], difference [0.021, 0.089].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.558 / 0.458 | 0.186 / 0.449 / 0.533 | [-0.164, -0.054], [0.026, 0.119] | 0.537 / 0.441 | [-0.08, 0.035], [-0.06, 0.026] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.02 / 0.073 / 0.806 | [-0.084, -0.033], [-0.015, 0.177] | 0.136 / 0.769 | [-0.03, 0.049], [-0.104, 0.17] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.017 / 0.061 / 0.792 | [0.003, 0.019], [0.007, 0.073] | 0.06 / 0.891 | [-0.016, 0.037], [-0.113, 0.333] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.752 [0.7–0.802], learned 0.777 [0.711–0.837], difference [-0.024, 0.069].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.706 / 0.2 | 0.186 / 0.63 / 0.257 | [-0.182, 0.026], [0.02, 0.093] | 0.655 / 0.185 | [-0.152, 0.039], [-0.043, 0.011] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.02 / 0.123 / 0.468 | [-0.141, -0.033], [-0.041, 0.177] | 0.226 / 0.438 | [-0.039, 0.076], [-0.077, 0.167] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.017 / 0.089 / 0.396 | [0.0, 0.016], [-0.103, 0.017] | 0.128 / 0.652 | [-0.01, 0.101], [-0.025, 0.457] |

Snapshots below the current level: 0.13 (with a river post at Siaga 2+: 0.022).

### logistic · volume-matched

Thresholds by test year: {'2019': {'Waspada': 0.0531, 'Siaga': 0.2259, 'Bahaya': 0.3512}, '2020': {'Waspada': 0.102, 'Siaga': 0.4938, 'Bahaya': 0.673}, '2021': {'Waspada': 0.1737, 'Siaga': 0.628, 'Bahaya': 0.8319}, '2025': {'Waspada': 0.1836, 'Siaga': 0.6701, 'Bahaya': 0.8404}}

**any flood**: ROC-AUC current 0.694 [0.663–0.723], learned 0.749 [0.706–0.787], difference [0.021, 0.089].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.558 / 0.458 | 0.397 / 0.643 / 0.358 | [0.028, 0.14], [-0.135, -0.066] | 0.537 / 0.441 | [-0.08, 0.035], [-0.06, 0.026] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.045 / 0.132 / 0.647 | [-0.029, 0.036], [-0.205, 0.057] | 0.136 / 0.769 | [-0.03, 0.049], [-0.104, 0.17] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.029 / 0.1 / 0.764 | [0.029, 0.072], [-0.137, 0.126] | 0.06 / 0.891 | [-0.016, 0.037], [-0.113, 0.333] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.752 [0.7–0.802], learned 0.777 [0.711–0.837], difference [-0.024, 0.069].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.706 / 0.2 | 0.397 / 0.779 / 0.149 | [-0.014, 0.162], [-0.075, -0.028] | 0.655 / 0.185 | [-0.152, 0.039], [-0.043, 0.011] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.045 / 0.243 / 0.41 | [-0.024, 0.097], [-0.097, 0.131] | 0.226 / 0.438 | [-0.039, 0.076], [-0.077, 0.167] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.029 / 0.187 / 0.494 | [0.053, 0.158], [-0.075, 0.186] | 0.128 / 0.652 | [-0.01, 0.101], [-0.025, 0.457] |

Snapshots below the current level: 0.056 (with a river post at Siaga 2+: 0.019).

### xgb_monotone · precision-matched

Thresholds by test year: {'2019': {'Waspada': None, 'Siaga': None, 'Bahaya': None}, '2020': {'Waspada': None, 'Siaga': None, 'Bahaya': None}, '2021': {'Waspada': 0.168, 'Siaga': None, 'Bahaya': None}, '2025': {'Waspada': 0.1592, 'Siaga': None, 'Bahaya': None}}

**any flood**: ROC-AUC current 0.694 [0.663–0.723], learned 0.775 [0.735–0.811], difference [0.05, 0.115].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.558 / 0.458 | 0.158 / 0.278 / 0.389 | [-0.346, -0.205], [-0.133, -0.001] | 0.555 / 0.45 | [-0.072, 0.06], [-0.052, 0.037] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.015 / 0.051 / 0.761 | [-0.103, -0.056], [-0.084, 0.154] | 0.11 / 0.62 | [-0.056, 0.02], [-0.242, 0.02] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.015 / 0.051 / 0.761 | [0.0, 0.0], [0.0, 0.0] | 0.057 / 0.848 | [-0.015, 0.028], [-0.079, 0.26] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.752 [0.7–0.802], learned 0.781 [0.725–0.834], difference [-0.015, 0.073].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.706 / 0.2 | 0.158 / 0.174 / 0.084 | [-0.642, -0.421], [-0.162, -0.073] | 0.685 / 0.191 | [-0.126, 0.086], [-0.037, 0.019] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.015 / 0.085 / 0.435 | [-0.176, -0.071], [-0.086, 0.178] | 0.115 / 0.223 | [-0.167, -0.016], [-0.294, -0.054] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.015 / 0.085 / 0.435 | [0.0, 0.0], [0.0, 0.0] | 0.068 / 0.348 | [-0.056, 0.018], [-0.265, 0.077] |

Snapshots below the current level: 0.177 (with a river post at Siaga 2+: 0.024).

### xgb_monotone · volume-matched

Thresholds by test year: {'2019': {'Waspada': 0.074, 'Siaga': 0.3185, 'Bahaya': 0.4234}, '2020': {'Waspada': 0.1054, 'Siaga': 0.4337, 'Bahaya': 0.5655}, '2021': {'Waspada': 0.1917, 'Siaga': 0.5546, 'Bahaya': 0.7272}, '2025': {'Waspada': 0.2164, 'Siaga': 0.6133, 'Bahaya': 0.7562}}

**any flood**: ROC-AUC current 0.694 [0.663–0.723], learned 0.775 [0.735–0.811], difference [0.05, 0.115].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.558 / 0.458 | 0.443 / 0.758 / 0.378 | [0.14, 0.26], [-0.116, -0.042] | 0.555 / 0.45 | [-0.072, 0.06], [-0.052, 0.037] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.052 / 0.174 / 0.739 | [0.007, 0.08], [-0.093, 0.122] | 0.11 / 0.62 | [-0.056, 0.02], [-0.242, 0.02] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.024 / 0.082 / 0.767 | [0.017, 0.046], [-0.078, 0.089] | 0.057 / 0.848 | [-0.015, 0.028], [-0.079, 0.26] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.752 [0.7–0.802], learned 0.781 [0.725–0.834], difference [-0.015, 0.073].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.706 / 0.2 | 0.443 / 0.838 / 0.144 | [0.043, 0.219], [-0.082, -0.033] | 0.685 / 0.191 | [-0.126, 0.086], [-0.037, 0.019] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.052 / 0.247 / 0.36 | [-0.03, 0.107], [-0.133, 0.058] | 0.115 / 0.223 | [-0.167, -0.016], [-0.294, -0.054] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.024 / 0.111 / 0.356 | [0.005, 0.052], [-0.182, 0.016] | 0.068 / 0.348 | [-0.056, 0.018], [-0.265, 0.077] |

Snapshots below the current level: 0.05 (with a river post at Siaga 2+: 0.014).

## lag 2 · 3090 test snapshots on 1062 days (flood days 0.221, large 0.076)

### tree · precision-matched

Thresholds by test year: {'2019': {'Waspada': None, 'Siaga': None, 'Bahaya': None}, '2020': {'Waspada': None, 'Siaga': None, 'Bahaya': None}, '2021': {'Waspada': 0.2205, 'Siaga': None, 'Bahaya': None}, '2025': {'Waspada': 0.3208, 'Siaga': 0.5217, 'Bahaya': None}}

**any flood**: ROC-AUC current 0.683 [0.653–0.713], learned 0.733 [0.695–0.77], difference [0.014, 0.09].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.521 / 0.464 | 0.132 / 0.242 / 0.405 | [-0.345, -0.215], [-0.127, 0.025] | 0.635 / 0.436 | [0.05, 0.186], [-0.078, 0.019] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.018 / 0.059 / 0.702 | [-0.096, -0.048], [-0.139, 0.084] | 0.113 / 0.524 | [-0.052, 0.019], [-0.319, -0.079] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.015 / 0.051 / 0.761 | [0.0, 0.0], [0.0, 0.0] | 0.048 / 0.55 | [-0.029, 0.027], [-0.44, 0.028] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.732 [0.68–0.784], learned 0.712 [0.663–0.763], difference [-0.067, 0.032].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.651 / 0.199 | 0.132 / 0.166 / 0.096 | [-0.592, -0.38], [-0.155, -0.057] | 0.74 / 0.175 | [-0.02, 0.208], [-0.052, 0.006] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.018 / 0.089 / 0.368 | [-0.174, -0.065], [-0.139, 0.088] | 0.094 / 0.15 | [-0.179, -0.046], [-0.348, -0.146] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.015 / 0.085 / 0.435 | [0.0, 0.0], [0.0, 0.0] | 0.055 / 0.217 | [-0.082, 0.028], [-0.41, -0.001] |

Snapshots below the current level: 0.181 (with a river post at Siaga 2+: 0.024).

### logistic · precision-matched

Thresholds by test year: {'2019': {'Waspada': None, 'Siaga': None, 'Bahaya': None}, '2020': {'Waspada': 0.5292, 'Siaga': 0.7626, 'Bahaya': None}, '2021': {'Waspada': 0.2056, 'Siaga': 0.7937, 'Bahaya': 0.8898}, '2025': {'Waspada': 0.1768, 'Siaga': 0.7953, 'Bahaya': 0.8418}}

**any flood**: ROC-AUC current 0.683 [0.653–0.713], learned 0.746 [0.704–0.784], difference [0.027, 0.098].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.521 / 0.464 | 0.118 / 0.275 / 0.514 | [-0.3, -0.189], [-0.012, 0.117] | 0.512 / 0.455 | [-0.071, 0.05], [-0.059, 0.036] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.022 / 0.082 / 0.824 | [-0.076, -0.023], [0.004, 0.188] | 0.139 / 0.785 | [-0.027, 0.05], [-0.075, 0.171] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.017 / 0.061 / 0.792 | [0.003, 0.019], [0.007, 0.073] | 0.06 / 0.891 | [-0.015, 0.034], [-0.11, 0.333] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.732 [0.68–0.784], learned 0.764 [0.693–0.828], difference [-0.015, 0.076].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.651 / 0.199 | 0.118 / 0.272 / 0.175 | [-0.476, -0.278], [-0.071, 0.021] | 0.655 / 0.2 | [-0.1, 0.095], [-0.031, 0.03] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.022 / 0.14 / 0.485 | [-0.127, -0.01], [-0.032, 0.205] | 0.226 / 0.438 | [-0.046, 0.093], [-0.087, 0.165] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.017 / 0.089 / 0.396 | [0.0, 0.016], [-0.103, 0.017] | 0.128 / 0.652 | [-0.008, 0.101], [-0.021, 0.432] |

Snapshots below the current level: 0.167 (with a river post at Siaga 2+: 0.022).

### logistic · volume-matched

Thresholds by test year: {'2019': {'Waspada': 0.0527, 'Siaga': 0.2081, 'Bahaya': 0.3709}, '2020': {'Waspada': 0.104, 'Siaga': 0.4867, 'Bahaya': 0.63}, '2021': {'Waspada': 0.1766, 'Siaga': 0.6395, 'Bahaya': 0.7938}, '2025': {'Waspada': 0.1924, 'Siaga': 0.6757, 'Bahaya': 0.8263}}

**any flood**: ROC-AUC current 0.683 [0.653–0.713], learned 0.746 [0.704–0.784], difference [0.027, 0.098].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.521 / 0.464 | 0.415 / 0.668 / 0.356 | [0.089, 0.201], [-0.147, -0.072] | 0.512 / 0.455 | [-0.071, 0.05], [-0.059, 0.036] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.048 / 0.145 / 0.664 | [-0.018, 0.049], [-0.186, 0.068] | 0.139 / 0.785 | [-0.027, 0.05], [-0.075, 0.171] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.03 / 0.104 / 0.755 | [0.033, 0.076], [-0.149, 0.123] | 0.06 / 0.891 | [-0.015, 0.034], [-0.11, 0.333] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.732 [0.68–0.784], learned 0.764 [0.693–0.828], difference [-0.015, 0.076].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.651 / 0.199 | 0.415 / 0.753 / 0.138 | [0.023, 0.18], [-0.087, -0.037] | 0.655 / 0.2 | [-0.1, 0.095], [-0.031, 0.03] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.048 / 0.26 / 0.409 | [-0.009, 0.117], [-0.096, 0.122] | 0.226 / 0.438 | [-0.046, 0.093], [-0.087, 0.165] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.03 / 0.2 / 0.5 | [0.066, 0.171], [-0.077, 0.201] | 0.128 / 0.652 | [-0.008, 0.101], [-0.021, 0.432] |

Snapshots below the current level: 0.054 (with a river post at Siaga 2+: 0.017).

### xgb_monotone · precision-matched

Thresholds by test year: {'2019': {'Waspada': None, 'Siaga': None, 'Bahaya': None}, '2020': {'Waspada': None, 'Siaga': None, 'Bahaya': None}, '2021': {'Waspada': 0.1526, 'Siaga': None, 'Bahaya': None}, '2025': {'Waspada': 0.151, 'Siaga': None, 'Bahaya': None}}

**any flood**: ROC-AUC current 0.683 [0.653–0.713], learned 0.769 [0.73–0.805], difference [0.053, 0.12].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.521 / 0.464 | 0.164 / 0.286 / 0.385 | [-0.299, -0.17], [-0.138, -0.012] | 0.529 / 0.463 | [-0.06, 0.071], [-0.051, 0.048] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.015 / 0.051 / 0.761 | [-0.103, -0.056], [-0.084, 0.154] | 0.116 / 0.642 | [-0.049, 0.026], [-0.217, 0.043] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.015 / 0.051 / 0.761 | [0.0, 0.0], [0.0, 0.0] | 0.057 / 0.848 | [-0.016, 0.029], [-0.077, 0.26] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.732 [0.68–0.784], learned 0.774 [0.713–0.827], difference [-0.002, 0.087].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.651 / 0.199 | 0.164 / 0.179 / 0.083 | [-0.576, -0.367], [-0.163, -0.074] | 0.655 / 0.198 | [-0.097, 0.11], [-0.03, 0.029] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.015 / 0.085 / 0.435 | [-0.176, -0.071], [-0.086, 0.178] | 0.106 / 0.203 | [-0.171, -0.027], [-0.312, -0.073] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.015 / 0.085 / 0.435 | [0.0, 0.0], [0.0, 0.0] | 0.068 / 0.348 | [-0.057, 0.019], [-0.273, 0.07] |

Snapshots below the current level: 0.161 (with a river post at Siaga 2+: 0.024).

### xgb_monotone · volume-matched

Thresholds by test year: {'2019': {'Waspada': 0.074, 'Siaga': 0.3635, 'Bahaya': 0.3924}, '2020': {'Waspada': 0.0948, 'Siaga': 0.4616, 'Bahaya': 0.5659}, '2021': {'Waspada': 0.2065, 'Siaga': 0.567, 'Bahaya': 0.73}, '2025': {'Waspada': 0.2285, 'Siaga': 0.6194, 'Bahaya': 0.7628}}

**any flood**: ROC-AUC current 0.683 [0.653–0.713], learned 0.769 [0.73–0.805], difference [0.053, 0.12].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.521 / 0.464 | 0.407 / 0.739 / 0.401 | [0.156, 0.278], [-0.103, -0.023] | 0.529 / 0.463 | [-0.06, 0.071], [-0.051, 0.048] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.043 / 0.148 / 0.765 | [-0.015, 0.049], [-0.058, 0.127] | 0.116 / 0.642 | [-0.049, 0.026], [-0.217, 0.043] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.022 / 0.075 / 0.75 | [0.012, 0.036], [-0.095, 0.07] | 0.057 / 0.848 | [-0.016, 0.029], [-0.077, 0.26] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.732 [0.68–0.784], learned 0.774 [0.713–0.827], difference [-0.002, 0.087].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.651 / 0.199 | 0.407 / 0.83 / 0.155 | [0.093, 0.269], [-0.069, -0.019] | 0.655 / 0.198 | [-0.097, 0.11], [-0.03, 0.029] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.043 / 0.217 / 0.386 | [-0.065, 0.086], [-0.116, 0.088] | 0.106 / 0.203 | [-0.171, -0.027], [-0.312, -0.073] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.022 / 0.102 / 0.353 | [0.004, 0.038], [-0.178, -0.003] | 0.068 / 0.348 | [-0.057, 0.019], [-0.273, 0.07] |

Snapshots below the current level: 0.052 (with a river post at Siaga 2+: 0.016).

## lag 3 · 3090 test snapshots on 1062 days (flood days 0.221, large 0.076)

### tree · precision-matched

Thresholds by test year: {'2019': {'Waspada': None, 'Siaga': None, 'Bahaya': None}, '2020': {'Waspada': None, 'Siaga': None, 'Bahaya': None}, '2021': {'Waspada': 0.2363, 'Siaga': 0.8478, 'Bahaya': 0.8478}, '2025': {'Waspada': 0.3913, 'Siaga': 0.5217, 'Bahaya': None}}

**any flood**: ROC-AUC current 0.685 [0.655–0.714], learned 0.743 [0.704–0.779], difference [0.023, 0.093].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.53 / 0.46 | 0.125 / 0.24 / 0.425 | [-0.354, -0.224], [-0.109, 0.047] | 0.605 / 0.458 | [0.009, 0.143], [-0.05, 0.043] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.02 / 0.064 / 0.721 | [-0.091, -0.041], [-0.117, 0.102] | 0.101 / 0.57 | [-0.064, 0.007], [-0.277, -0.041] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.016 / 0.057 / 0.78 | [0.0, 0.014], [0.0, 0.05] | 0.101 / 0.57 | [0.023, 0.083], [-0.351, -0.029] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.731 [0.68–0.784], learned 0.729 [0.674–0.78], difference [-0.051, 0.05].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.655 / 0.196 | 0.125 / 0.166 / 0.101 | [-0.597, -0.379], [-0.143, -0.046] | 0.74 / 0.193 | [-0.028, 0.203], [-0.033, 0.029] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.02 / 0.089 / 0.344 | [-0.174, -0.065], [-0.162, 0.06] | 0.085 / 0.165 | [-0.194, -0.045], [-0.352, -0.118] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.016 / 0.085 / 0.4 | [0.0, 0.0], [-0.09, 0.0] | 0.085 / 0.165 | [-0.044, 0.044], [-0.43, -0.125] |

Snapshots below the current level: 0.185 (with a river post at Siaga 2+: 0.024).

### logistic · precision-matched

Thresholds by test year: {'2019': {'Waspada': None, 'Siaga': None, 'Bahaya': None}, '2020': {'Waspada': 0.6515, 'Siaga': 0.7964, 'Bahaya': None}, '2021': {'Waspada': 0.2024, 'Siaga': 0.8007, 'Bahaya': 0.8897}, '2025': {'Waspada': 0.1714, 'Siaga': 0.8074, 'Bahaya': 0.9008}}

**any flood**: ROC-AUC current 0.685 [0.655–0.714], learned 0.745 [0.703–0.784], difference [0.026, 0.095].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.53 / 0.46 | 0.117 / 0.264 / 0.497 | [-0.321, -0.206], [-0.024, 0.108] | 0.518 / 0.447 | [-0.073, 0.045], [-0.061, 0.032] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.019 / 0.072 / 0.817 | [-0.084, -0.035], [-0.005, 0.184] | 0.139 / 0.785 | [-0.028, 0.049], [-0.073, 0.171] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.017 / 0.061 / 0.792 | [0.003, 0.019], [0.007, 0.073] | 0.06 / 0.891 | [-0.017, 0.034], [-0.11, 0.336] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.731 [0.68–0.784], learned 0.757 [0.686–0.824], difference [-0.026, 0.075].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.655 / 0.196 | 0.117 / 0.234 / 0.152 | [-0.524, -0.317], [-0.091, 0.004] | 0.66 / 0.196 | [-0.091, 0.1], [-0.029, 0.028] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.019 / 0.111 / 0.433 | [-0.15, -0.049], [-0.078, 0.149] | 0.213 / 0.413 | [-0.056, 0.068], [-0.101, 0.141] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.017 / 0.089 / 0.396 | [0.0, 0.016], [-0.103, 0.017] | 0.119 / 0.609 | [-0.014, 0.082], [-0.057, 0.414] |

Snapshots below the current level: 0.174 (with a river post at Siaga 2+: 0.022).

### logistic · volume-matched

Thresholds by test year: {'2019': {'Waspada': 0.0581, 'Siaga': 0.2236, 'Bahaya': 0.4037}, '2020': {'Waspada': 0.1043, 'Siaga': 0.4943, 'Bahaya': 0.6516}, '2021': {'Waspada': 0.1737, 'Siaga': 0.6455, 'Bahaya': 0.7962}, '2025': {'Waspada': 0.1877, 'Siaga': 0.6622, 'Bahaya': 0.8202}}

**any flood**: ROC-AUC current 0.685 [0.655–0.714], learned 0.745 [0.703–0.784], difference [0.026, 0.095].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.53 / 0.46 | 0.378 / 0.659 / 0.386 | [0.072, 0.177], [-0.112, -0.039] | 0.518 / 0.447 | [-0.073, 0.045], [-0.061, 0.032] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.046 / 0.136 / 0.66 | [-0.022, 0.039], [-0.196, 0.067] | 0.139 / 0.785 | [-0.028, 0.049], [-0.073, 0.171] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.027 / 0.098 / 0.807 | [0.028, 0.068], [-0.08, 0.149] | 0.06 / 0.891 | [-0.017, 0.034], [-0.11, 0.336] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.731 [0.68–0.784], learned 0.757 [0.686–0.824], difference [-0.026, 0.075].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.655 / 0.196 | 0.378 / 0.762 / 0.153 | [0.026, 0.185], [-0.066, -0.02] | 0.66 / 0.196 | [-0.091, 0.1], [-0.029, 0.028] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.046 / 0.238 / 0.397 | [-0.021, 0.086], [-0.107, 0.108] | 0.213 / 0.413 | [-0.056, 0.068], [-0.101, 0.141] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.027 / 0.179 / 0.506 | [0.05, 0.145], [-0.055, 0.189] | 0.119 / 0.609 | [-0.014, 0.082], [-0.057, 0.414] |

Snapshots below the current level: 0.059 (with a river post at Siaga 2+: 0.018).

### xgb_monotone · precision-matched

Thresholds by test year: {'2019': {'Waspada': None, 'Siaga': None, 'Bahaya': None}, '2020': {'Waspada': 0.1042, 'Siaga': None, 'Bahaya': None}, '2021': {'Waspada': 0.1628, 'Siaga': None, 'Bahaya': None}, '2025': {'Waspada': 0.1683, 'Siaga': None, 'Bahaya': None}}

**any flood**: ROC-AUC current 0.685 [0.655–0.714], learned 0.773 [0.733–0.808], difference [0.056, 0.12].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.53 / 0.46 | 0.332 / 0.649 / 0.431 | [0.055, 0.189], [-0.075, 0.017] | 0.537 / 0.455 | [-0.057, 0.068], [-0.052, 0.041] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.015 / 0.051 / 0.761 | [-0.103, -0.056], [-0.084, 0.154] | 0.116 / 0.642 | [-0.05, 0.025], [-0.216, 0.045] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.015 / 0.051 / 0.761 | [0.0, 0.0], [0.0, 0.0] | 0.059 / 0.833 | [-0.014, 0.03], [-0.083, 0.249] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.731 [0.68–0.784], learned 0.777 [0.711–0.831], difference [-0.004, 0.091].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.655 / 0.196 | 0.332 / 0.762 / 0.174 | [-0.014, 0.223], [-0.05, 0.009] | 0.677 / 0.197 | [-0.083, 0.12], [-0.027, 0.028] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.015 / 0.085 / 0.435 | [-0.176, -0.071], [-0.086, 0.178] | 0.111 / 0.211 | [-0.169, -0.02], [-0.302, -0.069] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.015 / 0.085 / 0.435 | [0.0, 0.0], [0.0, 0.0] | 0.072 / 0.354 | [-0.054, 0.025], [-0.263, 0.083] |

Snapshots below the current level: 0.094 (with a river post at Siaga 2+: 0.024).

### xgb_monotone · volume-matched

Thresholds by test year: {'2019': {'Waspada': 0.074, 'Siaga': 0.3587, 'Bahaya': 0.4147}, '2020': {'Waspada': 0.1053, 'Siaga': 0.4813, 'Bahaya': 0.5847}, '2021': {'Waspada': 0.2003, 'Siaga': 0.5792, 'Bahaya': 0.7267}, '2025': {'Waspada': 0.2336, 'Siaga': 0.6508, 'Bahaya': 0.7811}}

**any flood**: ROC-AUC current 0.685 [0.655–0.714], learned 0.773 [0.733–0.808], difference [0.056, 0.12].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.53 / 0.46 | 0.448 / 0.751 / 0.371 | [0.16, 0.279], [-0.127, -0.053] | 0.537 / 0.455 | [-0.057, 0.068], [-0.052, 0.041] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.044 / 0.146 / 0.741 | [-0.013, 0.047], [-0.089, 0.116] | 0.116 / 0.642 | [-0.05, 0.025], [-0.216, 0.045] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.022 / 0.076 / 0.776 | [0.013, 0.038], [-0.053, 0.089] | 0.059 / 0.833 | [-0.014, 0.03], [-0.083, 0.249] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.731 [0.68–0.784], learned 0.777 [0.711–0.831], difference [-0.004, 0.091].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.655 / 0.196 | 0.448 / 0.843 / 0.143 | [0.1, 0.278], [-0.079, -0.028] | 0.677 / 0.197 | [-0.083, 0.12], [-0.027, 0.028] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.044 / 0.221 / 0.385 | [-0.051, 0.079], [-0.11, 0.087] | 0.111 / 0.211 | [-0.169, -0.02], [-0.302, -0.069] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.022 / 0.102 / 0.358 | [0.004, 0.038], [-0.167, -0.003] | 0.072 / 0.354 | [-0.054, 0.025], [-0.263, 0.083] |

Snapshots below the current level: 0.053 (with a river post at Siaga 2+: 0.015).

