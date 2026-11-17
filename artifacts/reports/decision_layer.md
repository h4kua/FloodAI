# Learned decision layer vs the current rules

Generated 2026-11-17T13:19:35+00:00 by `scripts/train_decision_layer.py` on cuda (1000 day resamples).

Features: p, w_max_now, w_frac1_now, w_frac2_now, w_upstream_now, w_manggarai_now, w_max_d1, w_frac1_d1, w_frac2_d1, w_upstream_d1, w_manggarai_d1, today_mean, today_max, today_bogor, hour. Current = river rules (Siaga 3/2/1 -> Waspada/Siaga/Bahaya) + the daily model's Waspada. Learned: a flood score from one of three learners (depth-3 tree; logistic regression; XGBoost depth 2 with every feature monotone increasing), thresholds per level set on the training years (leave-one-year-out scores) at the precision the current level has there, so at equal precision the one catching more floods is better. A river post at Siaga 1 stays Bahaya. Test years 2019, 2020, 2021, 2025, each trained on earlier snapshots only. 'Equal volume' re-cuts the learned score on the test rows to the current alarm shares (a ranking check, not deployable).

Served: **xgb_monotone** (volume-matched thresholds), thresholds {'lag 1': {'PRE_ALERT': 0.20148, 'WARNING': 0.64573, 'DANGER': 0.79996}, 'lag 2': {'PRE_ALERT': 0.21218, 'WARNING': 0.64613, 'DANGER': 0.80498}, 'lag 3': {'PRE_ALERT': 0.20842, 'WARNING': 0.65572, 'DANGER': 0.80653}}.

## lag 1 · 3090 test snapshots on 1062 days (flood days 0.221, large 0.076)

### tree · precision-matched

Thresholds by test year: {'2019': {'Waspada': None, 'Siaga': None, 'Bahaya': None}, '2020': {'Waspada': 0.3333, 'Siaga': None, 'Bahaya': None}, '2021': {'Waspada': 0.4222, 'Siaga': None, 'Bahaya': None}, '2025': {'Waspada': 0.2995, 'Siaga': None, 'Bahaya': None}}

**any flood**: ROC-AUC current 0.694 [0.663–0.723], learned 0.745 [0.705–0.781], difference [0.018, 0.085].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.558 / 0.458 | 0.076 / 0.193 / 0.559 | [-0.419, -0.301], [0.017, 0.19] | 0.589 / 0.421 | [-0.033, 0.1], [-0.079, 0.005] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.015 / 0.051 / 0.761 | [-0.103, -0.056], [-0.084, 0.154] | 0.143 / 0.541 | [-0.032, 0.063], [-0.326, -0.058] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.015 / 0.051 / 0.761 | [0.0, 0.0], [0.0, 0.0] | 0.104 / 0.634 | [0.021, 0.087], [-0.294, 0.05] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.752 [0.7–0.802], learned 0.737 [0.68–0.789], difference [-0.065, 0.035].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.706 / 0.2 | 0.076 / 0.162 / 0.161 | [-0.653, -0.44], [-0.101, 0.022] | 0.723 / 0.178 | [-0.083, 0.128], [-0.049, 0.006] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.015 / 0.085 / 0.435 | [-0.176, -0.071], [-0.086, 0.178] | 0.119 / 0.155 | [-0.169, 0.0], [-0.358, -0.129] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.015 / 0.085 / 0.435 | [0.0, 0.0], [0.0, 0.0] | 0.102 / 0.214 | [-0.036, 0.07], [-0.379, -0.071] |

Snapshots below the current level: 0.21 (with a river post at Siaga 2+: 0.024).

### logistic · precision-matched

Thresholds by test year: {'2019': {'Waspada': 0.4699, 'Siaga': 0.6438, 'Bahaya': None}, '2020': {'Waspada': 0.0959, 'Siaga': 0.7069, 'Bahaya': 0.9417}, '2021': {'Waspada': 0.1738, 'Siaga': 0.5558, 'Bahaya': 0.7935}, '2025': {'Waspada': 0.1676, 'Siaga': 0.3471, 'Bahaya': 0.8045}}

**any flood**: ROC-AUC current 0.694 [0.663–0.723], learned 0.763 [0.722–0.8], difference [0.034, 0.103].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.558 / 0.458 | 0.253 / 0.542 / 0.474 | [-0.071, 0.037], [-0.025, 0.056] | 0.548 / 0.449 | [-0.069, 0.043], [-0.052, 0.03] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.05 / 0.165 / 0.724 | [0.006, 0.067], [-0.099, 0.101] | 0.142 / 0.802 | [-0.026, 0.051], [-0.058, 0.205] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.021 / 0.078 / 0.803 | [0.012, 0.046], [-0.033, 0.125] | 0.059 / 0.87 | [-0.019, 0.036], [-0.135, 0.319] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.752 [0.7–0.802], learned 0.782 [0.715–0.836], difference [-0.017, 0.076].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.706 / 0.2 | 0.253 / 0.698 / 0.21 | [-0.103, 0.084], [-0.016, 0.036] | 0.643 / 0.181 | [-0.169, 0.035], [-0.046, 0.007] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.05 / 0.238 / 0.359 | [-0.028, 0.094], [-0.133, 0.052] | 0.289 / 0.562 | [0.005, 0.16], [0.031, 0.302] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.021 / 0.123 / 0.439 | [0.008, 0.081], [-0.091, 0.113] | 0.119 / 0.609 | [-0.025, 0.102], [-0.08, 0.41] |

Snapshots below the current level: 0.109 (with a river post at Siaga 2+: 0.015).

### logistic · volume-matched

Thresholds by test year: {'2019': {'Waspada': 0.0531, 'Siaga': 0.2379, 'Bahaya': 0.395}, '2020': {'Waspada': 0.0936, 'Siaga': 0.4784, 'Bahaya': 0.7111}, '2021': {'Waspada': 0.1665, 'Siaga': 0.6765, 'Bahaya': 0.8358}, '2025': {'Waspada': 0.178, 'Siaga': 0.6967, 'Bahaya': 0.8734}}

**any flood**: ROC-AUC current 0.694 [0.663–0.723], learned 0.763 [0.722–0.8], difference [0.034, 0.103].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.558 / 0.458 | 0.428 / 0.643 / 0.332 | [0.028, 0.135], [-0.166, -0.091] | 0.548 / 0.449 | [-0.069, 0.043], [-0.052, 0.03] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.057 / 0.189 / 0.733 | [0.024, 0.099], [-0.105, 0.123] | 0.142 / 0.802 | [-0.026, 0.051], [-0.058, 0.205] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.036 / 0.126 / 0.782 | [0.049, 0.102], [-0.107, 0.145] | 0.059 / 0.87 | [-0.019, 0.036], [-0.135, 0.319] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.752 [0.7–0.802], learned 0.782 [0.715–0.836], difference [-0.017, 0.076].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.706 / 0.2 | 0.428 / 0.762 / 0.135 | [-0.034, 0.139], [-0.09, -0.042] | 0.643 / 0.181 | [-0.169, 0.035], [-0.046, 0.007] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.057 / 0.353 / 0.472 | [0.068, 0.227], [-0.035, 0.183] | 0.289 / 0.562 | [0.005, 0.16], [0.031, 0.302] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.036 / 0.217 / 0.464 | [0.076, 0.194], [-0.115, 0.165] | 0.119 / 0.609 | [-0.025, 0.102], [-0.08, 0.41] |

Snapshots below the current level: 0.079 (with a river post at Siaga 2+: 0.019).

### xgb_monotone · precision-matched

Thresholds by test year: {'2019': {'Waspada': 0.5234, 'Siaga': None, 'Bahaya': None}, '2020': {'Waspada': 0.0908, 'Siaga': None, 'Bahaya': None}, '2021': {'Waspada': 0.1552, 'Siaga': None, 'Bahaya': None}, '2025': {'Waspada': 0.1525, 'Siaga': 0.4369, 'Bahaya': None}}

**any flood**: ROC-AUC current 0.694 [0.663–0.723], learned 0.786 [0.748–0.821], difference [0.06, 0.126].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.558 / 0.458 | 0.293 / 0.597 / 0.45 | [-0.024, 0.103], [-0.053, 0.036] | 0.572 / 0.471 | [-0.045, 0.076], [-0.03, 0.058] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.043 / 0.113 / 0.575 | [-0.041, 0.009], [-0.244, -0.058] | 0.138 / 0.777 | [-0.027, 0.048], [-0.06, 0.175] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.015 / 0.051 / 0.761 | [0.0, 0.0], [0.0, 0.0] | 0.064 / 0.957 | [-0.01, 0.037], [0.038, 0.367] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.752 [0.7–0.802], learned 0.791 [0.728–0.844], difference [-0.007, 0.084].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.706 / 0.2 | 0.293 / 0.719 / 0.187 | [-0.083, 0.114], [-0.038, 0.013] | 0.685 / 0.194 | [-0.112, 0.068], [-0.032, 0.019] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.043 / 0.119 / 0.209 | [-0.142, -0.035], [-0.278, -0.108] | 0.2 / 0.388 | [-0.069, 0.061], [-0.123, 0.106] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.015 / 0.085 / 0.435 | [0.0, 0.0], [0.0, 0.0] | 0.098 / 0.5 | [-0.031, 0.063], [-0.13, 0.26] |

Snapshots below the current level: 0.1 (with a river post at Siaga 2+: 0.017).

### xgb_monotone · volume-matched

Thresholds by test year: {'2019': {'Waspada': 0.074, 'Siaga': 0.3496, 'Bahaya': 0.4707}, '2020': {'Waspada': 0.0851, 'Siaga': 0.4898, 'Bahaya': 0.6408}, '2021': {'Waspada': 0.1731, 'Siaga': 0.6227, 'Bahaya': 0.7609}, '2025': {'Waspada': 0.1932, 'Siaga': 0.6696, 'Bahaya': 0.8016}}

**any flood**: ROC-AUC current 0.694 [0.663–0.723], learned 0.786 [0.748–0.821], difference [0.06, 0.126].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.558 / 0.458 | 0.359 / 0.691 / 0.426 | [0.071, 0.193], [-0.071, 0.005] | 0.572 / 0.471 | [-0.045, 0.076], [-0.03, 0.058] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.064 / 0.22 / 0.758 | [0.051, 0.134], [-0.07, 0.13] | 0.138 / 0.777 | [-0.027, 0.048], [-0.06, 0.175] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.031 / 0.117 / 0.842 | [0.045, 0.092], [-0.014, 0.195] | 0.064 / 0.957 | [-0.01, 0.037], [0.038, 0.367] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.752 [0.7–0.802], learned 0.791 [0.728–0.844], difference [-0.007, 0.084].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.269 / 0.706 / 0.2 | 0.359 / 0.791 / 0.168 | [0.004, 0.167], [-0.055, -0.01] | 0.685 / 0.194 | [-0.112, 0.068], [-0.032, 0.019] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.064 / 0.362 / 0.429 | [0.08, 0.232], [-0.08, 0.126] | 0.2 / 0.388 | [-0.069, 0.061], [-0.123, 0.106] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.031 / 0.221 / 0.547 | [0.081, 0.198], [-0.013, 0.245] | 0.098 / 0.5 | [-0.031, 0.063], [-0.13, 0.26] |

Snapshots below the current level: 0.073 (with a river post at Siaga 2+: 0.014).

## lag 2 · 3090 test snapshots on 1062 days (flood days 0.221, large 0.076)

### tree · precision-matched

Thresholds by test year: {'2019': {'Waspada': None, 'Siaga': None, 'Bahaya': None}, '2020': {'Waspada': 0.2772, 'Siaga': None, 'Bahaya': None}, '2021': {'Waspada': 0.215, 'Siaga': None, 'Bahaya': None}, '2025': {'Waspada': 0.2242, 'Siaga': None, 'Bahaya': None}}

**any flood**: ROC-AUC current 0.683 [0.653–0.713], learned 0.74 [0.699–0.778], difference [0.017, 0.097].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.521 / 0.464 | 0.22 / 0.466 / 0.468 | [-0.116, 0.007], [-0.051, 0.061] | 0.514 / 0.438 | [-0.071, 0.06], [-0.078, 0.027] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.015 / 0.051 / 0.761 | [-0.103, -0.056], [-0.084, 0.154] | 0.113 / 0.616 | [-0.057, 0.027], [-0.241, 0.017] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.015 / 0.051 / 0.761 | [0.0, 0.0], [0.0, 0.0] | 0.044 / 0.652 | [-0.039, 0.026], [-0.395, 0.145] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.732 [0.68–0.784], learned 0.73 [0.67–0.784], difference [-0.053, 0.05].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.651 / 0.199 | 0.22 / 0.549 / 0.19 | [-0.201, 0.006], [-0.041, 0.025] | 0.613 / 0.18 | [-0.14, 0.063], [-0.049, 0.012] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.015 / 0.085 / 0.435 | [-0.176, -0.071], [-0.086, 0.178] | 0.106 / 0.2 | [-0.181, -0.015], [-0.322, -0.08] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.015 / 0.085 / 0.435 | [0.0, 0.0], [0.0, 0.0] | 0.043 / 0.217 | [-0.105, 0.018], [-0.439, 0.042] |

Snapshots below the current level: 0.139 (with a river post at Siaga 2+: 0.024).

### logistic · precision-matched

Thresholds by test year: {'2019': {'Waspada': 0.4654, 'Siaga': None, 'Bahaya': None}, '2020': {'Waspada': 0.0926, 'Siaga': 0.6439, 'Bahaya': 0.943}, '2021': {'Waspada': 0.1607, 'Siaga': 0.5917, 'Bahaya': 0.8036}, '2025': {'Waspada': 0.1647, 'Siaga': 0.3689, 'Bahaya': 0.8152}}

**any flood**: ROC-AUC current 0.683 [0.653–0.713], learned 0.763 [0.722–0.801], difference [0.045, 0.113].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.521 / 0.464 | 0.266 / 0.561 / 0.465 | [-0.016, 0.091], [-0.042, 0.041] | 0.529 / 0.471 | [-0.053, 0.064], [-0.043, 0.05] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.048 / 0.157 / 0.723 | [-0.005, 0.059], [-0.102, 0.093] | 0.142 / 0.802 | [-0.025, 0.051], [-0.06, 0.207] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.021 / 0.078 / 0.803 | [0.012, 0.046], [-0.033, 0.125] | 0.059 / 0.87 | [-0.02, 0.036], [-0.139, 0.321] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.732 [0.68–0.784], learned 0.781 [0.714–0.835], difference [0.002, 0.095].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.651 / 0.199 | 0.266 / 0.715 / 0.204 | [-0.027, 0.161], [-0.021, 0.032] | 0.643 / 0.197 | [-0.114, 0.092], [-0.031, 0.027] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.048 / 0.23 / 0.365 | [-0.047, 0.088], [-0.13, 0.062] | 0.277 / 0.537 | [-0.008, 0.142], [0.008, 0.274] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.021 / 0.123 / 0.439 | [0.008, 0.081], [-0.091, 0.113] | 0.119 / 0.609 | [-0.023, 0.099], [-0.074, 0.408] |

Snapshots below the current level: 0.097 (with a river post at Siaga 2+: 0.016).

### logistic · volume-matched

Thresholds by test year: {'2019': {'Waspada': 0.0519, 'Siaga': 0.2327, 'Bahaya': 0.3926}, '2020': {'Waspada': 0.0941, 'Siaga': 0.4645, 'Bahaya': 0.7081}, '2021': {'Waspada': 0.1712, 'Siaga': 0.6518, 'Bahaya': 0.844}, '2025': {'Waspada': 0.1887, 'Siaga': 0.685, 'Bahaya': 0.8741}}

**any flood**: ROC-AUC current 0.683 [0.653–0.713], learned 0.763 [0.722–0.801], difference [0.045, 0.113].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.521 / 0.464 | 0.428 / 0.643 / 0.332 | [0.069, 0.168], [-0.169, -0.096] | 0.529 / 0.471 | [-0.053, 0.064], [-0.043, 0.05] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.061 / 0.198 / 0.718 | [0.031, 0.11], [-0.116, 0.107] | 0.142 / 0.802 | [-0.025, 0.051], [-0.06, 0.207] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.036 / 0.13 / 0.802 | [0.054, 0.109], [-0.084, 0.16] | 0.059 / 0.87 | [-0.02, 0.036], [-0.139, 0.321] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.732 [0.68–0.784], learned 0.781 [0.714–0.835], difference [0.002, 0.095].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.651 / 0.199 | 0.428 / 0.77 / 0.137 | [0.038, 0.202], [-0.086, -0.038] | 0.643 / 0.197 | [-0.114, 0.092], [-0.031, 0.027] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.061 / 0.353 / 0.441 | [0.069, 0.221], [-0.061, 0.15] | 0.277 / 0.537 | [-0.008, 0.142], [0.008, 0.274] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.036 / 0.226 / 0.477 | [0.082, 0.205], [-0.105, 0.177] | 0.119 / 0.609 | [-0.023, 0.099], [-0.074, 0.408] |

Snapshots below the current level: 0.068 (with a river post at Siaga 2+: 0.018).

### xgb_monotone · precision-matched

Thresholds by test year: {'2019': {'Waspada': 0.5572, 'Siaga': None, 'Bahaya': None}, '2020': {'Waspada': 0.0793, 'Siaga': None, 'Bahaya': None}, '2021': {'Waspada': 0.1455, 'Siaga': 0.6362, 'Bahaya': None}, '2025': {'Waspada': 0.1568, 'Siaga': 0.4069, 'Bahaya': None}}

**any flood**: ROC-AUC current 0.683 [0.653–0.713], learned 0.788 [0.751–0.822], difference [0.073, 0.138].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.521 / 0.464 | 0.306 / 0.608 / 0.439 | [0.025, 0.152], [-0.072, 0.02] | 0.546 / 0.486 | [-0.034, 0.084], [-0.023, 0.07] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.051 / 0.132 / 0.573 | [-0.026, 0.032], [-0.25, -0.058] | 0.136 / 0.769 | [-0.03, 0.045], [-0.073, 0.167] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.015 / 0.051 / 0.761 | [0.0, 0.0], [0.0, 0.0] | 0.064 / 0.957 | [-0.01, 0.037], [0.038, 0.367] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.732 [0.68–0.784], learned 0.794 [0.733–0.846], difference [0.017, 0.106].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.651 / 0.199 | 0.306 / 0.736 / 0.183 | [-0.013, 0.191], [-0.042, 0.012] | 0.66 / 0.202 | [-0.082, 0.109], [-0.024, 0.031] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.051 / 0.136 / 0.204 | [-0.129, -0.012], [-0.287, -0.112] | 0.191 / 0.372 | [-0.083, 0.054], [-0.139, 0.093] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.015 / 0.085 / 0.435 | [0.0, 0.0], [0.0, 0.0] | 0.098 / 0.5 | [-0.033, 0.064], [-0.128, 0.255] |

Snapshots below the current level: 0.092 (with a river post at Siaga 2+: 0.016).

### xgb_monotone · volume-matched

Thresholds by test year: {'2019': {'Waspada': 0.074, 'Siaga': 0.3757, 'Bahaya': 0.5053}, '2020': {'Waspada': 0.0936, 'Siaga': 0.4959, 'Bahaya': 0.6484}, '2021': {'Waspada': 0.1947, 'Siaga': 0.6094, 'Bahaya': 0.7465}, '2025': {'Waspada': 0.2078, 'Siaga': 0.6643, 'Bahaya': 0.8065}}

**any flood**: ROC-AUC current 0.683 [0.653–0.713], learned 0.788 [0.751–0.822], difference [0.073, 0.138].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.521 / 0.464 | 0.342 / 0.671 / 0.433 | [0.089, 0.21], [-0.071, 0.007] | 0.546 / 0.486 | [-0.034, 0.084], [-0.023, 0.07] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.063 / 0.214 / 0.749 | [0.046, 0.126], [-0.079, 0.124] | 0.136 / 0.769 | [-0.03, 0.045], [-0.073, 0.167] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.03 / 0.113 / 0.828 | [0.04, 0.086], [-0.03, 0.176] | 0.064 / 0.957 | [-0.01, 0.037], [0.038, 0.367] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.732 [0.68–0.784], learned 0.794 [0.733–0.846], difference [0.017, 0.106].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.248 / 0.651 / 0.199 | 0.342 / 0.783 / 0.174 | [0.053, 0.215], [-0.048, -0.003] | 0.66 / 0.202 | [-0.082, 0.109], [-0.024, 0.031] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.063 / 0.357 / 0.431 | [0.076, 0.225], [-0.075, 0.132] | 0.191 / 0.372 | [-0.083, 0.054], [-0.139, 0.093] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.03 / 0.2 / 0.505 | [0.063, 0.175], [-0.049, 0.195] | 0.098 / 0.5 | [-0.033, 0.064], [-0.128, 0.255] |

Snapshots below the current level: 0.071 (with a river post at Siaga 2+: 0.014).

## lag 3 · 3090 test snapshots on 1062 days (flood days 0.221, large 0.076)

### tree · precision-matched

Thresholds by test year: {'2019': {'Waspada': None, 'Siaga': None, 'Bahaya': None}, '2020': {'Waspada': 0.2381, 'Siaga': None, 'Bahaya': None}, '2021': {'Waspada': 0.2697, 'Siaga': None, 'Bahaya': None}, '2025': {'Waspada': 0.2265, 'Siaga': 0.6744, 'Bahaya': None}}

**any flood**: ROC-AUC current 0.685 [0.655–0.714], learned 0.73 [0.689–0.767], difference [0.008, 0.082].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.53 / 0.46 | 0.174 / 0.406 / 0.514 | [-0.185, -0.062], [0.0, 0.107] | 0.605 / 0.435 | [0.013, 0.139], [-0.068, 0.02] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.015 / 0.051 / 0.761 | [-0.103, -0.056], [-0.084, 0.154] | 0.149 / 0.57 | [-0.02, 0.065], [-0.279, -0.034] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.015 / 0.051 / 0.761 | [0.0, 0.0], [0.0, 0.0] | 0.044 / 0.652 | [-0.039, 0.026], [-0.395, 0.145] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.731 [0.68–0.784], learned 0.735 [0.67–0.795], difference [-0.05, 0.059].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.655 / 0.196 | 0.174 / 0.536 / 0.234 | [-0.222, -0.014], [-0.0, 0.076] | 0.74 / 0.183 | [-0.01, 0.19], [-0.04, 0.016] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.015 / 0.085 / 0.435 | [-0.176, -0.071], [-0.086, 0.178] | 0.136 / 0.179 | [-0.148, 0.01], [-0.326, -0.113] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.015 / 0.085 / 0.435 | [0.0, 0.0], [0.0, 0.0] | 0.043 / 0.217 | [-0.105, 0.018], [-0.439, 0.042] |

Snapshots below the current level: 0.156 (with a river post at Siaga 2+: 0.024).

### logistic · precision-matched

Thresholds by test year: {'2019': {'Waspada': 0.4804, 'Siaga': None, 'Bahaya': None}, '2020': {'Waspada': 0.0886, 'Siaga': 0.7079, 'Bahaya': 0.9402}, '2021': {'Waspada': 0.1649, 'Siaga': 0.6405, 'Bahaya': 0.8286}, '2025': {'Waspada': 0.1635, 'Siaga': 0.5369, 'Bahaya': 0.8246}}

**any flood**: ROC-AUC current 0.685 [0.655–0.714], learned 0.762 [0.721–0.8], difference [0.042, 0.111].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.53 / 0.46 | 0.272 / 0.574 / 0.467 | [-0.009, 0.095], [-0.035, 0.044] | 0.533 / 0.463 | [-0.056, 0.059], [-0.043, 0.047] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.034 / 0.122 / 0.798 | [-0.039, 0.022], [-0.021, 0.166] | 0.142 / 0.802 | [-0.024, 0.049], [-0.054, 0.204] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.021 / 0.075 / 0.797 | [0.01, 0.042], [-0.039, 0.121] | 0.059 / 0.87 | [-0.019, 0.036], [-0.135, 0.321] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.731 [0.68–0.784], learned 0.777 [0.709–0.832], difference [-0.004, 0.092].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.655 / 0.196 | 0.272 / 0.732 / 0.205 | [-0.014, 0.171], [-0.016, 0.036] | 0.643 / 0.192 | [-0.117, 0.087], [-0.032, 0.026] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.034 / 0.196 / 0.442 | [-0.074, 0.051], [-0.06, 0.152] | 0.281 / 0.545 | [0.0, 0.146], [0.022, 0.281] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.021 / 0.119 / 0.438 | [0.005, 0.076], [-0.091, 0.105] | 0.119 / 0.609 | [-0.022, 0.1], [-0.077, 0.407] |

Snapshots below the current level: 0.103 (with a river post at Siaga 2+: 0.02).

### logistic · volume-matched

Thresholds by test year: {'2019': {'Waspada': 0.0586, 'Siaga': 0.2376, 'Bahaya': 0.4187}, '2020': {'Waspada': 0.0964, 'Siaga': 0.46, 'Bahaya': 0.7367}, '2021': {'Waspada': 0.1697, 'Siaga': 0.6642, 'Bahaya': 0.8517}, '2025': {'Waspada': 0.1859, 'Siaga': 0.6916, 'Bahaya': 0.8692}}

**any flood**: ROC-AUC current 0.685 [0.655–0.714], learned 0.762 [0.721–0.8], difference [0.042, 0.111].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.53 / 0.46 | 0.416 / 0.638 / 0.339 | [0.053, 0.158], [-0.157, -0.085] | 0.533 / 0.463 | [-0.056, 0.059], [-0.043, 0.047] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.06 / 0.192 / 0.712 | [0.027, 0.103], [-0.126, 0.101] | 0.142 / 0.802 | [-0.024, 0.049], [-0.054, 0.204] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.032 / 0.117 / 0.8 | [0.043, 0.091], [-0.095, 0.154] | 0.059 / 0.87 | [-0.019, 0.036], [-0.135, 0.321] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.731 [0.68–0.784], learned 0.777 [0.709–0.832], difference [-0.004, 0.092].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.655 / 0.196 | 0.416 / 0.757 / 0.139 | [0.018, 0.182], [-0.081, -0.033] | 0.643 / 0.192 | [-0.117, 0.087], [-0.032, 0.026] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.06 / 0.336 / 0.429 | [0.051, 0.204], [-0.074, 0.141] | 0.281 / 0.545 | [0.0, 0.146], [0.022, 0.281] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.032 / 0.2 / 0.47 | [0.064, 0.172], [-0.1, 0.16] | 0.119 / 0.609 | [-0.022, 0.1], [-0.077, 0.407] |

Snapshots below the current level: 0.076 (with a river post at Siaga 2+: 0.019).

### xgb_monotone · precision-matched

Thresholds by test year: {'2019': {'Waspada': 0.4686, 'Siaga': None, 'Bahaya': None}, '2020': {'Waspada': 0.0733, 'Siaga': None, 'Bahaya': None}, '2021': {'Waspada': 0.1459, 'Siaga': 0.5024, 'Bahaya': None}, '2025': {'Waspada': 0.1538, 'Siaga': 0.4342, 'Bahaya': None}}

**any flood**: ROC-AUC current 0.685 [0.655–0.714], learned 0.784 [0.745–0.819], difference [0.066, 0.131].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.53 / 0.46 | 0.316 / 0.631 / 0.441 | [0.038, 0.165], [-0.062, 0.024] | 0.549 / 0.476 | [-0.041, 0.078], [-0.029, 0.064] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.061 / 0.16 / 0.583 | [-0.006, 0.071], [-0.249, -0.042] | 0.138 / 0.777 | [-0.028, 0.049], [-0.064, 0.174] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.015 / 0.051 / 0.761 | [0.0, 0.0], [0.0, 0.0] | 0.063 / 0.935 | [-0.011, 0.036], [0.01, 0.341] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.731 [0.68–0.784], learned 0.787 [0.721–0.841], difference [0.009, 0.103].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.655 / 0.196 | 0.316 / 0.762 / 0.183 | [0.015, 0.206], [-0.038, 0.013] | 0.668 / 0.199 | [-0.088, 0.108], [-0.024, 0.032] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.061 / 0.149 / 0.187 | [-0.12, 0.005], [-0.305, -0.121] | 0.196 / 0.38 | [-0.075, 0.056], [-0.133, 0.1] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.015 / 0.085 / 0.435 | [0.0, 0.0], [0.0, 0.0] | 0.102 / 0.522 | [-0.027, 0.069], [-0.1, 0.278] |

Snapshots below the current level: 0.091 (with a river post at Siaga 2+: 0.016).

### xgb_monotone · volume-matched

Thresholds by test year: {'2019': {'Waspada': 0.074, 'Siaga': 0.3785, 'Bahaya': 0.5141}, '2020': {'Waspada': 0.0917, 'Siaga': 0.5201, 'Bahaya': 0.6709}, '2021': {'Waspada': 0.1813, 'Siaga': 0.6288, 'Bahaya': 0.7717}, '2025': {'Waspada': 0.2031, 'Siaga': 0.6685, 'Bahaya': 0.8045}}

**any flood**: ROC-AUC current 0.685 [0.655–0.714], learned 0.784 [0.745–0.819], difference [0.066, 0.131].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.53 / 0.46 | 0.344 / 0.671 / 0.431 | [0.081, 0.196], [-0.067, 0.012] | 0.549 / 0.476 | [-0.041, 0.078], [-0.029, 0.064] |
| >= Siaga | 0.039 / 0.129 / 0.727 | 0.062 / 0.212 / 0.751 | [0.047, 0.122], [-0.076, 0.129] | 0.138 / 0.777 | [-0.028, 0.049], [-0.064, 0.174] |
| >= Bahaya | 0.015 / 0.051 / 0.761 | 0.027 / 0.101 / 0.821 | [0.032, 0.071], [-0.035, 0.169] | 0.063 / 0.935 | [-0.011, 0.036], [0.01, 0.341] |

**large flood (>= 5 kecamatan)**: ROC-AUC current 0.731 [0.68–0.784], learned 0.787 [0.721–0.841], difference [0.009, 0.103].

| Level | Current share / recall / precision | Learned share / recall / precision | Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | Equal volume − current recall, precision (95 %) |
|---|---|---|---|---|---|
| >= Waspada | 0.255 / 0.655 / 0.196 | 0.344 / 0.77 / 0.17 | [0.031, 0.205], [-0.048, -0.004] | 0.668 / 0.199 | [-0.088, 0.108], [-0.024, 0.032] |
| >= Siaga | 0.039 / 0.204 / 0.397 | 0.062 / 0.349 / 0.425 | [0.066, 0.216], [-0.08, 0.12] | 0.196 / 0.38 | [-0.075, 0.056], [-0.133, 0.1] |
| >= Bahaya | 0.015 / 0.085 / 0.435 | 0.027 / 0.179 / 0.5 | [0.049, 0.145], [-0.054, 0.19] | 0.102 / 0.522 | [-0.027, 0.069], [-0.1, 0.278] |

Snapshots below the current level: 0.072 (with a river post at Siaga 2+: 0.014).

