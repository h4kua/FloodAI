# Thesis experiments

Generated 2026-11-10T13:47:44+00:00 by `scripts/thesis_experiments.py` on cuda. Nothing here is served.

Rows: kecamatan-days of the 42 model kecamatan, IMERG rain, BPBD flood dates. Train 2020–2021, validate 2022, test 2023 to Sep 2025 (BPBD dates are only partly readable after 2022, so test precision is a lower bound).

Rows train / validate / test: 30702 / 15330 / 42168; flood rows 1027 / 544 / 990 (test prevalence 0.0235, the no-skill PR-AUC).

## Exp 1a · Feature sets (XGBoost, default settings)

| Features | PR-AUC on 2022 | Test ROC-AUC [95 %] | Test PR-AUC [95 %] |
|---|---|---|---|
| F1 rain (today, yesterday, 3 days) | 0.057 | 0.724 [0.694–0.753] | 0.067 [0.049–0.099] |
| F2 + antecedent rain (7 days, API) | 0.064 | 0.726 [0.695–0.754] | 0.073 [0.049–0.107] |
| F3 + upstream rain (Bogor, Depok) | 0.069 | 0.725 [0.693–0.755] | 0.084 [0.056–0.122] |
| F4 + place and season | 0.116 | 0.834 [0.814–0.852] | 0.147 [0.109–0.196] |
| F5 + hourly intensity | 0.112 | 0.838 [0.817–0.857] | 0.177 [0.131–0.231] |
| F6 + drivers (soil moisture, MJO, ENSO, northerly surge, spring tide) | 0.104 | 0.844 [0.826–0.862] | 0.172 [0.123–0.228] |

Best on 2022: **F4 + place and season**.

## Exp 1b · Models on that feature set

| Model | PR-AUC on 2022 | Test ROC-AUC [95 %] | Test PR-AUC [95 %] |
|---|---|---|---|
| baseline: rain that day (d0) | 0.063 | 0.743 [0.711–0.77] | 0.082 [0.057–0.114] |
| baseline: climatology | 0.047 | 0.729 [0.695–0.761] | 0.068 [0.054–0.084] |
| logistic | 0.111 | 0.832 [0.812–0.85] | 0.161 [0.116–0.209] |
| random_forest | 0.102 | 0.843 [0.823–0.861] | 0.154 [0.109–0.208] |
| mlp | 0.092 | 0.825 [0.806–0.843] | 0.119 [0.093–0.152] |
| xgboost | 0.116 | 0.834 [0.814–0.852] | 0.147 [0.109–0.196] |
| xgboost_tuned | 0.13 | 0.839 [0.819–0.857] | 0.162 [0.116–0.217] |

Tuned XGBoost: 300 random-search trials in 455.2 s, best PR-AUC on 2022 0.1298. Chosen model (best PR-AUC on 2022): **xgboost_tuned**.

Paired differences on the test years (95 %, bootstrap over dates):

| Comparison | ROC-AUC difference | PR-AUC difference |
|---|---|---|
| xgboost_tuned minus baseline: rain that day (d0) | [0.077, 0.12] | [0.048, 0.118] |
| xgboost_tuned minus baseline: climatology | [0.078, 0.148] | [0.053, 0.145] |
| xgboost_tuned minus logistic | [-0.005, 0.02] | [-0.027, 0.032] |
| xgboost_tuned minus random_forest | [-0.012, 0.006] | [-0.013, 0.026] |
| xgboost_tuned minus mlp | [-0.001, 0.03] | [0.008, 0.086] |
| xgboost_tuned minus xgboost | [0.001, 0.01] | [0.0, 0.032] |

## Exp 2 · Warning thresholds (chosen on 2022, scored on the test years)

| Rule | Threshold | Recall | Precision | Alarms | Alarms per kecamatan-month | Missed floods |
|---|---|---|---|---|---|---|
| model: budget 0.5 alarm(s) per kecamatan per month | 0.7503 | 0.211 | 0.189 | 1107 | 0.8 | 781 |
| model: budget 1 alarm(s) per kecamatan per month | 0.6759 | 0.32 | 0.171 | 1859 | 1.34 | 673 |
| model: budget 2 alarm(s) per kecamatan per month | 0.5595 | 0.449 | 0.135 | 3304 | 2.38 | 545 |
| model: budget 4 alarm(s) per kecamatan per month | 0.4154 | 0.567 | 0.096 | 5822 | 4.2 | 429 |
| model: best F1 on 2022 | 0.5557 | 0.456 | 0.134 | 3359 | 2.42 | 539 |
| model: highest recall with precision >= 0.30 on 2022 | 0.8194 | 0.135 | 0.265 | 505 | 0.36 | 856 |
| rain: rain that day >= 50 mm (BMKG heavy) | 50.0 | 0.085 | 0.124 | 680 | 0.49 | 906 |
| rain: rain that day >= 100 mm (BMKG very heavy) | 100.0 | 0.011 | 0.733 | 15 | 0.01 | 979 |
| rain: same number of alarms as the model's 1-per-month budget | 35.155 | 0.217 | 0.115 | 1864 | 1.34 | 775 |

## Exp 3 · Rules vs model vs hybrid, Jakarta-days 2025-01-01 to 2025-09-30

Water levels: 15 of 19 posts have DSDA Siaga bands (without: PA. PASAR IKAN (LAUT), PS. CIPINANG HULU, TANGKI, WADUK PLUIT); 197 missing readings. One reading a day; the file does not say at what time.

Posts at Siaga 3 or above on more than half of the days (left out of "rules", kept in "rules, all 15 posts"): PA. FLUSHING ANCOL (59 %), PA. MARINA (KALI) (68 %), PA. MARINA (LAUT) (96 %), PA.HEK (95 %). "rules" = the highest Siaga level of the other posts; "hybrid" = the higher of "rules" and the model.

Days at each level (0 Safe, 1 Watch, 2 Alert, 3 Danger): rules, all 15 posts {'0': 9, '1': 9, '2': 210, '3': 45}; rules {'0': 142, '1': 82, '2': 26, '3': 23}; model {'0': 192, '1': 24, '2': 28, '3': 29}; hybrid {'0': 111, '1': 73, '2': 44, '3': 45}

| Label · warning level | Approach | Warning days | Flood days | Recall | Recall incl. day before | Precision | False-alarm days |
|---|---|---|---|---|---|---|---|
| any BPBD flood record | >= Watch | rules, all 15 posts | 264 | 128 | 0.961 | 0.992 | 0.466 | 141 |
| any BPBD flood record | >= Watch | rules | 131 | 128 | 0.57 | 0.656 | 0.557 | 58 |
| any BPBD flood record | >= Watch | model | 81 | 128 | 0.367 | 0.516 | 0.58 | 34 |
| any BPBD flood record | >= Watch | hybrid | 162 | 128 | 0.664 | 0.766 | 0.525 | 77 |
| any BPBD flood record | >= Watch | hybrid − rules, 95 % | | | [0.045, 0.145] | | [-0.073, 0.005] | |
| any BPBD flood record | >= Alert | rules, all 15 posts | 255 | 128 | 0.945 | 0.992 | 0.475 | 134 |
| any BPBD flood record | >= Alert | rules | 49 | 128 | 0.32 | 0.406 | 0.837 | 8 |
| any BPBD flood record | >= Alert | model | 57 | 128 | 0.258 | 0.406 | 0.579 | 24 |
| any BPBD flood record | >= Alert | hybrid | 89 | 128 | 0.445 | 0.562 | 0.64 | 32 |
| any BPBD flood record | >= Alert | hybrid − rules, 95 % | | | [0.075, 0.186] | | [-0.304, -0.104] | |
| any BPBD flood record | Danger | rules, all 15 posts | 45 | 128 | 0.297 | 0.445 | 0.844 | 7 |
| any BPBD flood record | Danger | rules | 23 | 128 | 0.156 | 0.242 | 0.87 | 3 |
| any BPBD flood record | Danger | model | 29 | 128 | 0.117 | 0.227 | 0.517 | 14 |
| any BPBD flood record | Danger | hybrid | 45 | 128 | 0.219 | 0.367 | 0.622 | 17 |
| any BPBD flood record | Danger | hybrid − rules, 95 % | | | [0.023, 0.102] | | [-0.4, -0.114] | |
| large flood (>= 10 RW records) | >= Watch | rules, all 15 posts | 264 | 13 | 1.0 | 1.0 | 0.049 | 251 |
| large flood (>= 10 RW records) | >= Watch | rules | 131 | 13 | 0.923 | 0.923 | 0.092 | 119 |
| large flood (>= 10 RW records) | >= Watch | model | 81 | 13 | 0.769 | 1.0 | 0.123 | 71 |
| large flood (>= 10 RW records) | >= Watch | hybrid | 162 | 13 | 0.923 | 1.0 | 0.074 | 150 |
| large flood (>= 10 RW records) | >= Watch | hybrid − rules, 95 % | | | [0.0, 0.0] | | [-0.03, -0.008] | |
| large flood (>= 10 RW records) | >= Alert | rules, all 15 posts | 255 | 13 | 1.0 | 1.0 | 0.051 | 242 |
| large flood (>= 10 RW records) | >= Alert | rules | 49 | 13 | 0.846 | 0.923 | 0.224 | 38 |
| large flood (>= 10 RW records) | >= Alert | model | 57 | 13 | 0.692 | 0.923 | 0.158 | 48 |
| large flood (>= 10 RW records) | >= Alert | hybrid | 89 | 13 | 0.846 | 1.0 | 0.124 | 78 |
| large flood (>= 10 RW records) | >= Alert | hybrid − rules, 95 % | | | [0.0, 0.0] | | [-0.16, -0.046] | |
| large flood (>= 10 RW records) | Danger | rules, all 15 posts | 45 | 13 | 0.846 | 0.923 | 0.244 | 34 |
| large flood (>= 10 RW records) | Danger | rules | 23 | 13 | 0.615 | 0.692 | 0.348 | 15 |
| large flood (>= 10 RW records) | Danger | model | 29 | 13 | 0.538 | 0.692 | 0.241 | 22 |
| large flood (>= 10 RW records) | Danger | hybrid | 45 | 13 | 0.692 | 0.846 | 0.2 | 36 |
| large flood (>= 10 RW records) | Danger | hybrid − rules, 95 % | | | [0.0, 0.286] | | [-0.286, -0.03] | |
| any BPBD flood record | model with as many warning days as the rules | rules | 131 | 128 | 0.57 | 0.656 | 0.557 | 58 |
| any BPBD flood record | model with as many warning days as the rules | model | 131 | 128 | 0.555 | 0.688 | 0.542 | 60 |
| large flood (>= 10 RW records) | model with as many warning days as the rules | rules | 131 | 13 | 0.923 | 0.923 | 0.092 | 119 |
| large flood (>= 10 RW records) | model with as many warning days as the rules | model | 131 | 13 | 0.769 | 1.0 | 0.076 | 121 |

Run time 797.3 s.
