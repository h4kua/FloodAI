# Daily kecamatan model for the website (IMERG Early)

Generated 2026-11-13T06:29:49+00:00 by `scripts/train_daily_live_model.py` on cuda. 199416 kecamatan-days 2013-2025, 4830 with a BPBD flood, 63126 with water levels of the previous day.

Rain through D-L only (IMERG Early reaches Giovanni about a day late). Rolling origin: each test year is scored by a model trained on earlier years. 95 % intervals resample test dates.

## 2016-2022 (complete labels): 2513 floods, prevalence 0.0234

| Model | ROC-AUC [95 %] | PR-AUC [95 %] |
|---|---|---|
| place and season | 0.735 [0.715–0.756] | 0.065 [0.054–0.079] |
| lag 1 | 0.808 [0.79–0.825] | 0.101 [0.081–0.128] |
| lag 1 + water | 0.807 [0.789–0.824] | 0.096 [0.079–0.119] |
| lag 2 | 0.786 [0.769–0.804] | 0.079 [0.064–0.098] |
| lag 2 + water | 0.789 [0.77–0.808] | 0.081 [0.066–0.1] |
| lag 3 | 0.774 [0.754–0.794] | 0.077 [0.063–0.099] |
| lag 3 + water | 0.774 [0.756–0.794] | 0.071 [0.059–0.088] |

## 2023-2025 (partial labels): 1048 floods, prevalence 0.0228

| Model | ROC-AUC [95 %] | PR-AUC [95 %] |
|---|---|---|
| place and season | 0.769 [0.747–0.791] | 0.063 [0.05–0.078] |
| lag 1 | 0.836 [0.817–0.853] | 0.124 [0.09–0.167] |
| lag 1 + water | 0.833 [0.813–0.85] | 0.122 [0.089–0.163] |
| lag 2 | 0.799 [0.779–0.816] | 0.072 [0.056–0.092] |
| lag 2 + water | 0.806 [0.784–0.823] | 0.082 [0.063–0.108] |
| lag 3 | 0.79 [0.769–0.811] | 0.068 [0.055–0.086] |
| lag 3 + water | 0.798 [0.777–0.817] | 0.075 [0.059–0.095] |

## water years 2017-2021, 2025: 1973 floods, prevalence 0.0214

| Model | ROC-AUC [95 %] | PR-AUC [95 %] |
|---|---|---|
| place and season | 0.769 [0.75–0.787] | 0.07 [0.057–0.087] |
| lag 1 | 0.826 [0.807–0.845] | 0.115 [0.093–0.147] |
| lag 1 + water | 0.821 [0.799–0.839] | 0.105 [0.086–0.134] |
| lag 2 | 0.8 [0.78–0.819] | 0.081 [0.065–0.102] |
| lag 2 + water | 0.803 [0.781–0.823] | 0.086 [0.071–0.108] |
| lag 3 | 0.8 [0.779–0.82] | 0.085 [0.068–0.108] |
| lag 3 + water | 0.798 [0.778–0.818] | 0.079 [0.065–0.099] |

## Paired differences (b minus a, 95 %)

| Block | a | b | ROC-AUC | PR-AUC |
|---|---|---|---|---|
| 2016-2022 (complete labels) | place and season | lag 2 | [0.036, 0.065] | [0.005, 0.025] |
| 2016-2022 (complete labels) | lag 2 | lag 2 + water | [-0.006, 0.012] | [-0.004, 0.008] |
| 2016-2022 (complete labels) | lag 3 | lag 3 + water | [-0.008, 0.008] | [-0.016, 0.001] |
| 2016-2022 (complete labels) | lag 1 + water | lag 2 + water | [-0.03, -0.005] | [-0.027, -0.004] |
| 2016-2022 (complete labels) | lag 2 + water | lag 3 + water | [-0.027, -0.002] | [-0.018, -0.002] |
| 2023-2025 (partial labels) | place and season | lag 2 | [0.014, 0.047] | [-0.001, 0.023] |
| 2023-2025 (partial labels) | lag 2 | lag 2 + water | [-0.003, 0.016] | [0.003, 0.019] |
| 2023-2025 (partial labels) | lag 3 | lag 3 + water | [-0.002, 0.017] | [-0.0, 0.014] |
| 2023-2025 (partial labels) | lag 1 + water | lag 2 + water | [-0.041, -0.014] | [-0.066, -0.022] |
| 2023-2025 (partial labels) | lag 2 + water | lag 3 + water | [-0.021, 0.006] | [-0.019, 0.001] |
| water years 2017-2021, 2025 | place and season | lag 2 | [0.016, 0.046] | [-0.001, 0.023] |
| water years 2017-2021, 2025 | lag 2 | lag 2 + water | [-0.009, 0.014] | [-0.002, 0.016] |
| water years 2017-2021, 2025 | lag 3 | lag 3 + water | [-0.013, 0.009] | [-0.018, 0.005] |
| water years 2017-2021, 2025 | lag 1 + water | lag 2 + water | [-0.032, -0.007] | [-0.036, -0.007] |
| water years 2017-2021, 2025 | lag 2 + water | lag 3 + water | [-0.019, 0.009] | [-0.017, 0.003] |

## Served models: calibration and city tiers

### lag 1 + water

Kecamatan ECE 0.01 → 0.0 after isotonic, Brier 0.0217. City (highest kecamatan) ROC-AUC 2016-2022 0.7; share of days with a flood somewhere 0.217.

| Tier | Threshold | Days a month (2016-2022) | Recall | Precision |
|---|---|---|---|---|
| pre_alert | 0.0889 | 7.96 | 0.417 | 0.345 |

Siaga and Bahaya: not raised by the model (threshold 1.0). For reference, other alarm budgets:

| Budget | Threshold | Recall | Precision |
|---|---|---|---|
| 8 days a month | 0.0836 | 0.507 | 0.348 |
| 4 days a month | 0.1351 | 0.244 | 0.351 |
| 2 days a month | 0.2056 | 0.181 | 0.412 |
| 1 days a month | 0.2397 | 0.116 | 0.577 |

### lag 2 + water

Kecamatan ECE 0.0104 → 0.0 after isotonic, Brier 0.0219. City (highest kecamatan) ROC-AUC 2016-2022 0.67; share of days with a flood somewhere 0.217.

| Tier | Threshold | Days a month (2016-2022) | Recall | Precision |
|---|---|---|---|---|
| pre_alert | 0.0822 | 8.38 | 0.399 | 0.314 |

Siaga and Bahaya: not raised by the model (threshold 1.0). For reference, other alarm budgets:

| Budget | Threshold | Recall | Precision |
|---|---|---|---|
| 8 days a month | 0.0822 | 0.399 | 0.314 |
| 4 days a month | 0.127 | 0.211 | 0.344 |
| 2 days a month | 0.1705 | 0.144 | 0.432 |
| 1 days a month | 0.1705 | 0.144 | 0.432 |

### lag 3 + water

Kecamatan ECE 0.0106 → 0.0 after isotonic, Brier 0.022. City (highest kecamatan) ROC-AUC 2016-2022 0.661; share of days with a flood somewhere 0.217.

| Tier | Threshold | Days a month (2016-2022) | Recall | Precision |
|---|---|---|---|---|
| pre_alert | 0.0735 | 11.55 | 0.516 | 0.295 |

Siaga and Bahaya: not raised by the model (threshold 1.0). For reference, other alarm budgets:

| Budget | Threshold | Recall | Precision |
|---|---|---|---|
| 8 days a month | 0.0735 | 0.516 | 0.295 |
| 4 days a month | 0.1122 | 0.229 | 0.324 |
| 2 days a month | 0.1412 | 0.117 | 0.332 |
| 1 days a month | 0.1412 | 0.117 | 0.332 |

