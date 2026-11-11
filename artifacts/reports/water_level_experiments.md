# Water levels in the model, and a learned decision layer vs the rules

Generated 2026-11-10T18:28:52+00:00 by `scripts/water_level_experiments.py` on cuda. Nothing here is served.

City-days with water levels (at least 8 river posts): 2016: 58, 2017: 74, 2018: 242, 2019: 331, 2020: 318, 2021: 140, 2025: 351.

## Part A · Water levels as model features (kecamatan-days)

| Test | Rows | Floods | F4 ROC-AUC | F4 + water ROC-AUC | F4 PR-AUC | F4 + water PR-AUC |
|---|---|---|---|---|---|---|
| 2019 | 13902 | 126 | 0.883 | 0.899 | 0.073 | 0.135 |
| 2020 | 13356 | 560 | 0.752 | 0.789 | 0.105 | 0.16 |
| 2021 | 5880 | 85 | 0.866 | 0.896 | 0.116 | 0.191 |

Pooled 2019–2021: F4 ROC-AUC 0.778 [0.749–0.806], PR-AUC 0.078 [0.059–0.105]; F4 + water ROC-AUC 0.81 [0.784–0.837], PR-AUC 0.131 [0.097–0.182]. Difference (95 %): ROC-AUC [0.02, 0.046], PR-AUC [0.032, 0.084].

## Part B · City-day warnings, test years 2019, 2020, 2021, 2025

| Year | Days | Flood days | Large-flood days | ROC-AUC rules | ROC-AUC rules (informative) | ROC-AUC model | ROC-AUC learned |
|---|---|---|---|---|---|---|---|
| 2019 | 331 | 45 | 9 | 0.683 | 0.772 | 0.901 | 0.882 |
| 2020 | 318 | 94 | 44 | 0.751 | 0.773 | 0.724 | 0.741 |
| 2021 | 140 | 26 | 4 | 0.864 | 0.859 | 0.756 | 0.761 |
| 2025 | 264 | 123 | 19 | 0.627 | 0.638 | 0.644 | 0.67 |

Posts left out of the informative-post rules (share of training days at Siaga 3+): test 2019: HEK 0.84, ISTIQLAL 0.74, JEMBATANMERAH 0.88; test 2020: HEK 0.92, ISTIQLAL 0.77, JEMBATANMERAH 0.94; test 2021: HEK 0.68, ISTIQLAL 0.66, JEMBATANMERAH 0.94; test 2025: HEK 0.66, ISTIQLAL 0.58, JEMBATANMERAH 0.84.

Each approach at its own levels (thresholds from the training days):

| Label · level | Approach | Warning days | Flood days | Recall | Recall incl. day before | Precision | False alarms |
|---|---|---|---|---|---|---|---|
| any flood | >= Watch | rules | 995 | 288 | 0.993 | 1.0 | 0.287 | 709 |
| any flood | >= Watch | rules (informative posts) | 493 | 288 | 0.715 | 0.795 | 0.418 | 287 |
| any flood | >= Watch | model | 357 | 288 | 0.587 | 0.67 | 0.473 | 188 |
| any flood | >= Watch | hybrid | 997 | 288 | 0.993 | 1.0 | 0.287 | 711 |
| any flood | >= Watch | hybrid (informative posts) | 616 | 288 | 0.812 | 0.872 | 0.38 | 382 |
| any flood | >= Watch | learned | 389 | 288 | 0.646 | 0.736 | 0.478 | 203 |
| any flood | >= Watch | learned − rules (informative posts), 95 % | | | [-0.123, -0.022] | | [0.022, 0.1] | |
| any flood | >= Watch | learned − hybrid (informative posts), 95 % | | | [-0.211, -0.125] | | [0.066, 0.131] | |
| any flood | >= Watch | hybrid (informative posts) − rules (informative posts), 95 % | | | [0.064, 0.132] | | [-0.057, -0.019] | |
| any flood | >= Alert | rules | 640 | 288 | 0.642 | 0.729 | 0.289 | 455 |
| any flood | >= Alert | rules (informative posts) | 128 | 288 | 0.309 | 0.406 | 0.695 | 39 |
| any flood | >= Alert | model | 193 | 288 | 0.389 | 0.451 | 0.58 | 81 |
| any flood | >= Alert | hybrid | 681 | 288 | 0.698 | 0.781 | 0.295 | 480 |
| any flood | >= Alert | hybrid (informative posts) | 269 | 288 | 0.538 | 0.625 | 0.576 | 114 |
| any flood | >= Alert | learned | 326 | 288 | 0.576 | 0.66 | 0.509 | 160 |
| any flood | >= Alert | learned − rules (informative posts), 95 % | | | [0.207, 0.327] | | [-0.261, -0.113] | |
| any flood | >= Alert | learned − hybrid (informative posts), 95 % | | | [-0.003, 0.08] | | [-0.106, -0.029] | |
| any flood | >= Alert | hybrid (informative posts) − rules (informative posts), 95 % | | | [0.179, 0.279] | | [-0.182, -0.06] | |
| any flood | Danger | rules | 138 | 288 | 0.285 | 0.375 | 0.594 | 56 |
| any flood | Danger | rules (informative posts) | 54 | 288 | 0.132 | 0.198 | 0.704 | 16 |
| any flood | Danger | model | 122 | 288 | 0.253 | 0.333 | 0.598 | 49 |
| any flood | Danger | hybrid | 219 | 288 | 0.417 | 0.521 | 0.548 | 99 |
| any flood | Danger | hybrid (informative posts) | 160 | 288 | 0.337 | 0.448 | 0.606 | 63 |
| any flood | Danger | learned | 179 | 288 | 0.368 | 0.451 | 0.592 | 73 |
| any flood | Danger | learned − rules (informative posts), 95 % | | | [0.179, 0.292] | | [-0.231, 0.016] | |
| any flood | Danger | learned − hybrid (informative posts), 95 % | | | [-0.023, 0.084] | | [-0.079, 0.052] | |
| any flood | Danger | hybrid (informative posts) − rules (informative posts), 95 % | | | [0.16, 0.249] | | [-0.191, 0.012] | |
| large flood (>= 5 kecamatan) | >= Watch | rules | 995 | 76 | 0.987 | 1.0 | 0.075 | 920 |
| large flood (>= 5 kecamatan) | >= Watch | rules (informative posts) | 493 | 76 | 0.934 | 0.947 | 0.144 | 422 |
| large flood (>= 5 kecamatan) | >= Watch | model | 357 | 76 | 0.816 | 0.855 | 0.174 | 295 |
| large flood (>= 5 kecamatan) | >= Watch | hybrid | 997 | 76 | 0.987 | 1.0 | 0.075 | 922 |
| large flood (>= 5 kecamatan) | >= Watch | hybrid (informative posts) | 616 | 76 | 0.947 | 0.961 | 0.117 | 544 |
| large flood (>= 5 kecamatan) | >= Watch | learned | 389 | 76 | 0.882 | 0.882 | 0.172 | 322 |
| large flood (>= 5 kecamatan) | >= Watch | learned − rules (informative posts), 95 % | | | [-0.116, 0.012] | | [0.012, 0.046] | |
| large flood (>= 5 kecamatan) | >= Watch | learned − hybrid (informative posts), 95 % | | | [-0.133, 0.0] | | [0.039, 0.074] | |
| large flood (>= 5 kecamatan) | >= Watch | hybrid (informative posts) − rules (informative posts), 95 % | | | [0.0, 0.042] | | [-0.036, -0.02] | |
| large flood (>= 5 kecamatan) | >= Alert | rules | 640 | 76 | 0.855 | 0.895 | 0.102 | 575 |
| large flood (>= 5 kecamatan) | >= Alert | rules (informative posts) | 128 | 76 | 0.553 | 0.618 | 0.328 | 86 |
| large flood (>= 5 kecamatan) | >= Alert | model | 193 | 76 | 0.684 | 0.724 | 0.269 | 141 |
| large flood (>= 5 kecamatan) | >= Alert | hybrid | 681 | 76 | 0.895 | 0.895 | 0.1 | 613 |
| large flood (>= 5 kecamatan) | >= Alert | hybrid (informative posts) | 269 | 76 | 0.829 | 0.855 | 0.234 | 206 |
| large flood (>= 5 kecamatan) | >= Alert | learned | 326 | 76 | 0.829 | 0.842 | 0.193 | 263 |
| large flood (>= 5 kecamatan) | >= Alert | learned − rules (informative posts), 95 % | | | [0.169, 0.4] | | [-0.196, -0.073] | |
| large flood (>= 5 kecamatan) | >= Alert | learned − hybrid (informative posts), 95 % | | | [-0.036, 0.041] | | [-0.061, -0.023] | |
| large flood (>= 5 kecamatan) | >= Alert | hybrid (informative posts) − rules (informative posts), 95 % | | | [0.177, 0.388] | | [-0.147, -0.038] | |
| large flood (>= 5 kecamatan) | Danger | rules | 138 | 76 | 0.539 | 0.592 | 0.297 | 97 |
| large flood (>= 5 kecamatan) | Danger | rules (informative posts) | 54 | 76 | 0.263 | 0.316 | 0.37 | 34 |
| large flood (>= 5 kecamatan) | Danger | model | 122 | 76 | 0.474 | 0.592 | 0.295 | 86 |
| large flood (>= 5 kecamatan) | Danger | hybrid | 219 | 76 | 0.697 | 0.789 | 0.242 | 166 |
| large flood (>= 5 kecamatan) | Danger | hybrid (informative posts) | 160 | 76 | 0.579 | 0.724 | 0.275 | 116 |
| large flood (>= 5 kecamatan) | Danger | learned | 179 | 76 | 0.711 | 0.737 | 0.302 | 125 |
| large flood (>= 5 kecamatan) | Danger | learned − rules (informative posts), 95 % | | | [0.319, 0.566] | | [-0.187, 0.049] | |
| large flood (>= 5 kecamatan) | Danger | learned − hybrid (informative posts), 95 % | | | [0.026, 0.242] | | [-0.024, 0.078] | |
| large flood (>= 5 kecamatan) | Danger | hybrid (informative posts) − rules (informative posts), 95 % | | | [0.212, 0.425] | | [-0.2, 0.007] | |

### Same number of warning days as the informative-post rules, per level

| Label · days | Approach | Warning days | Recall | Recall incl. day before | Precision |
|---|---|---|---|---|---|
| any flood | 493 days, as many as rules >= Watch | rules (informative posts) | 493 | 0.715 | 0.795 | 0.418 |
| any flood | 493 days, as many as rules >= Watch | model | 493 | 0.747 | 0.826 | 0.436 |
| any flood | 493 days, as many as rules >= Watch | learned | 493 | 0.667 | 0.757 | 0.389 |
| any flood | 493 days, as many as rules >= Watch | learned minus rules (informative posts), 95 % | | [-0.106, 0.007] | | [-0.065, 0.008] |
| large flood (>= 5 kecamatan) | 493 days, as many as rules >= Watch | rules (informative posts) | 493 | 0.934 | 0.947 | 0.144 |
| large flood (>= 5 kecamatan) | 493 days, as many as rules >= Watch | model | 493 | 0.842 | 0.895 | 0.13 |
| large flood (>= 5 kecamatan) | 493 days, as many as rules >= Watch | learned | 493 | 0.855 | 0.882 | 0.132 |
| large flood (>= 5 kecamatan) | 493 days, as many as rules >= Watch | learned minus rules (informative posts), 95 % | | [-0.15, -0.013] | | [-0.027, 0.002] |
| any flood | 128 days, as many as rules >= Alert | rules (informative posts) | 128 | 0.309 | 0.406 | 0.695 |
| any flood | 128 days, as many as rules >= Alert | model | 128 | 0.274 | 0.365 | 0.617 |
| any flood | 128 days, as many as rules >= Alert | learned | 128 | 0.281 | 0.354 | 0.633 |
| any flood | 128 days, as many as rules >= Alert | learned minus rules (informative posts), 95 % | | [-0.082, 0.028] | | [-0.154, 0.029] |
| large flood (>= 5 kecamatan) | 128 days, as many as rules >= Alert | rules (informative posts) | 128 | 0.553 | 0.618 | 0.328 |
| large flood (>= 5 kecamatan) | 128 days, as many as rules >= Alert | model | 128 | 0.5 | 0.618 | 0.297 |
| large flood (>= 5 kecamatan) | 128 days, as many as rules >= Alert | learned | 128 | 0.618 | 0.632 | 0.367 |
| large flood (>= 5 kecamatan) | 128 days, as many as rules >= Alert | learned minus rules (informative posts), 95 % | | [-0.056, 0.189] | | [-0.034, 0.114] |
| any flood | 54 days, as many as rules >= Danger | rules (informative posts) | 54 | 0.132 | 0.198 | 0.704 |
| any flood | 54 days, as many as rules >= Danger | model | 54 | 0.118 | 0.156 | 0.63 |
| any flood | 54 days, as many as rules >= Danger | learned | 54 | 0.128 | 0.153 | 0.685 |
| any flood | 54 days, as many as rules >= Danger | learned minus rules (informative posts), 95 % | | [-0.053, 0.047] | | [-0.172, 0.134] |
| large flood (>= 5 kecamatan) | 54 days, as many as rules >= Danger | rules (informative posts) | 54 | 0.263 | 0.316 | 0.37 |
| large flood (>= 5 kecamatan) | 54 days, as many as rules >= Danger | model | 54 | 0.224 | 0.276 | 0.315 |
| large flood (>= 5 kecamatan) | 54 days, as many as rules >= Danger | learned | 54 | 0.289 | 0.329 | 0.407 |
| large flood (>= 5 kecamatan) | 54 days, as many as rules >= Danger | learned minus rules (informative posts), 95 % | | [-0.125, 0.15] | | [-0.13, 0.185] |

### The learned decision trees (one per test year)

Test 2019:

```text
|--- model_p <= 0.42
|   |--- model_p <= 0.13
|   |   |--- class: 0
|   |--- model_p >  0.13
|   |   |--- model_p <= 0.23
|   |   |   |--- class: 0
|   |   |--- model_p >  0.23
|   |   |   |--- class: 0
|--- model_p >  0.42
|   |--- river_n2 <= 1.50
|   |   |--- model_p <= 0.78
|   |   |   |--- class: 0
|   |   |--- model_p >  0.78
|   |   |   |--- class: 1
|   |--- river_n2 >  1.50
|   |   |--- model_p <= 0.69
|   |   |   |--- class: 1
|   |   |--- model_p >  0.69
|   |   |   |--- class: 1
```

Test 2020:

```text
|--- model_p <= 0.41
|   |--- model_p <= 0.13
|   |   |--- class: 0
|   |--- model_p >  0.13
|   |   |--- river_n1_prev <= 2.50
|   |   |   |--- class: 0
|   |   |--- river_n1_prev >  2.50
|   |   |   |--- class: 0
|--- model_p >  0.41
|   |--- model_p <= 0.78
|   |   |--- river_n1 <= 2.50
|   |   |   |--- class: 0
|   |   |--- river_n1 >  2.50
|   |   |   |--- class: 1
|   |--- model_p >  0.78
|   |   |--- river_max <= 2.50
|   |   |   |--- class: 1
|   |   |--- river_max >  2.50
|   |   |   |--- class: 1
```

Test 2021:

```text
|--- model_p <= 0.36
|   |--- model_p <= 0.13
|   |   |--- model_p <= 0.02
|   |   |   |--- class: 0
|   |   |--- model_p >  0.02
|   |   |   |--- class: 0
|   |--- model_p >  0.13
|   |   |--- river_n2 <= 1.50
|   |   |   |--- class: 0
|   |   |--- river_n2 >  1.50
|   |   |   |--- class: 1
|--- model_p >  0.36
|   |--- model_p <= 0.78
|   |   |--- river_n2 <= 1.50
|   |   |   |--- class: 0
|   |   |--- river_n2 >  1.50
|   |   |   |--- class: 1
|   |--- model_p >  0.78
|   |   |--- river_max <= 2.50
|   |   |   |--- class: 1
|   |   |--- river_max >  2.50
|   |   |   |--- class: 1
```

Test 2025:

```text
|--- model_p <= 0.36
|   |--- model_p <= 0.13
|   |   |--- model_p <= 0.02
|   |   |   |--- class: 0
|   |   |--- model_p >  0.02
|   |   |   |--- class: 0
|   |--- model_p >  0.13
|   |   |--- river_n2 <= 1.50
|   |   |   |--- class: 0
|   |   |--- river_n2 >  1.50
|   |   |   |--- class: 1
|--- model_p >  0.36
|   |--- river_n1 <= 3.50
|   |   |--- model_p <= 0.79
|   |   |   |--- class: 0
|   |   |--- model_p >  0.79
|   |   |   |--- class: 1
|   |--- river_n1 >  3.50
|   |   |--- model_p <= 0.73
|   |   |   |--- class: 1
|   |   |--- model_p >  0.73
|   |   |   |--- class: 1
```

Run time 63.4 s.
