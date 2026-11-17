# Large flood days: can the live daily model justify Siaga?

Generated 2026-11-17T11:45:17+00:00 by `scripts/large_flood_experiment.py` on cuda (1000 day resamples). Nothing here is served.

City scores, out of sample: **max** = highest kecamatan probability (served now), **sum** = expected number of flooded kecamatan, **city** = XGBoost on city days trained on the large label. Alarm thresholds are the block's own quantiles (slightly optimistic).

## lag 1 (rain through D-1) · 2016-2022 (complete labels) · 2557 days

| Label | Days (share) | Score | ROC-AUC [95 %] | PR-AUC [95 %] |
|---|---|---|---|---|
| any flood | 554 (0.217) | max | 0.7 [0.677–0.723] | 0.367 [0.333–0.409] |
| any flood | 554 (0.217) | sum | 0.701 [0.676–0.725] | 0.369 [0.332–0.411] |
| any flood | 554 (0.217) | city | 0.56 [0.533–0.588] | 0.301 [0.267–0.336] |
| large (>= 5 kecamatan) | 174 (0.068) | max | 0.744 [0.708–0.776] | 0.171 [0.135–0.218] |
| large (>= 5 kecamatan) | 174 (0.068) | sum | 0.739 [0.703–0.772] | 0.174 [0.137–0.229] |
| large (>= 5 kecamatan) | 174 (0.068) | city | 0.594 [0.546–0.641] | 0.134 [0.097–0.181] |
| very large (>= 10 kecamatan) | 65 (0.025) | max | 0.751 [0.7–0.801] | 0.084 [0.056–0.135] |
| very large (>= 10 kecamatan) | 65 (0.025) | sum | 0.754 [0.7–0.806] | 0.1 [0.065–0.168] |
| very large (>= 10 kecamatan) | 65 (0.025) | city | 0.618 [0.537–0.693] | 0.06 [0.038–0.108] |

Paired differences (95 %):

- any flood: sum - max ROC-AUC [-0.007, 0.007], PR-AUC [-0.011, 0.014]; city - max ROC-AUC [-0.174, -0.109], PR-AUC [-0.103, -0.034]; city - sum ROC-AUC [-0.171, -0.114], PR-AUC [-0.098, -0.041]
- large (>= 5 kecamatan): sum - max ROC-AUC [-0.015, 0.006], PR-AUC [-0.01, 0.021]; city - max ROC-AUC [-0.202, -0.097], PR-AUC [-0.074, 0.001]; city - sum ROC-AUC [-0.192, -0.099], PR-AUC [-0.075, -0.005]
- very large (>= 10 kecamatan): sum - max ROC-AUC [-0.012, 0.015], PR-AUC [0.003, 0.044]; city - max ROC-AUC [-0.214, -0.055], PR-AUC [-0.059, 0.008]; city - sum ROC-AUC [-0.214, -0.062], PR-AUC [-0.086, -0.01]

| Label | Score | Alarms a month | Alarm days | Recall | Precision | Precision for any flood |
|---|---|---|---|---|---|---|
| large (>= 5 kecamatan) | max | 8 a month | 672 | 0.557 | 0.144 | 0.345 |
| large (>= 5 kecamatan) | max | 4 a month | 336 | 0.316 | 0.164 | 0.369 |
| large (>= 5 kecamatan) | max | 2 a month | 168 | 0.253 | 0.262 | 0.494 |
| large (>= 5 kecamatan) | max | 1 a month | 84 | 0.138 | 0.286 | 0.56 |
| large (>= 5 kecamatan) | sum | 8 a month | 672 | 0.552 | 0.143 | 0.356 |
| large (>= 5 kecamatan) | sum | 4 a month | 336 | 0.351 | 0.182 | 0.387 |
| large (>= 5 kecamatan) | sum | 2 a month | 168 | 0.23 | 0.238 | 0.458 |
| large (>= 5 kecamatan) | sum | 1 a month | 84 | 0.138 | 0.286 | 0.571 |
| large (>= 5 kecamatan) | city | 8 a month | 672 | 0.385 | 0.1 | 0.28 |
| large (>= 5 kecamatan) | city | 4 a month | 336 | 0.259 | 0.134 | 0.333 |
| large (>= 5 kecamatan) | city | 2 a month | 168 | 0.19 | 0.196 | 0.417 |
| large (>= 5 kecamatan) | city | 1 a month | 84 | 0.098 | 0.202 | 0.476 |
| very large (>= 10 kecamatan) | max | 8 a month | 672 | 0.569 | 0.055 | 0.345 |
| very large (>= 10 kecamatan) | max | 4 a month | 336 | 0.385 | 0.074 | 0.369 |
| very large (>= 10 kecamatan) | max | 2 a month | 168 | 0.323 | 0.125 | 0.494 |
| very large (>= 10 kecamatan) | max | 1 a month | 84 | 0.215 | 0.167 | 0.56 |
| very large (>= 10 kecamatan) | sum | 8 a month | 672 | 0.538 | 0.052 | 0.356 |
| very large (>= 10 kecamatan) | sum | 4 a month | 336 | 0.446 | 0.086 | 0.387 |
| very large (>= 10 kecamatan) | sum | 2 a month | 168 | 0.354 | 0.137 | 0.458 |
| very large (>= 10 kecamatan) | sum | 1 a month | 84 | 0.215 | 0.167 | 0.571 |
| very large (>= 10 kecamatan) | city | 8 a month | 672 | 0.4 | 0.039 | 0.28 |
| very large (>= 10 kecamatan) | city | 4 a month | 336 | 0.323 | 0.062 | 0.333 |
| very large (>= 10 kecamatan) | city | 2 a month | 168 | 0.246 | 0.095 | 0.417 |
| very large (>= 10 kecamatan) | city | 1 a month | 84 | 0.123 | 0.095 | 0.476 |

## lag 1 (rain through D-1) · 2023-2025 (partial labels) · 1096 days

| Label | Days (share) | Score | ROC-AUC [95 %] | PR-AUC [95 %] |
|---|---|---|---|---|
| any flood | 362 (0.33) | max | 0.638 [0.604–0.669] | 0.46 [0.411–0.514] |
| any flood | 362 (0.33) | sum | 0.636 [0.602–0.668] | 0.456 [0.407–0.511] |
| any flood | 362 (0.33) | city | 0.632 [0.597–0.663] | 0.469 [0.418–0.519] |
| large (>= 5 kecamatan) | 64 (0.058) | max | 0.797 [0.738–0.848] | 0.268 [0.178–0.395] |
| large (>= 5 kecamatan) | 64 (0.058) | sum | 0.804 [0.747–0.853] | 0.253 [0.168–0.381] |
| large (>= 5 kecamatan) | 64 (0.058) | city | 0.79 [0.736–0.837] | 0.248 [0.158–0.368] |
| very large (>= 10 kecamatan) | 18 (0.016) | max | 0.827 [0.731–0.911] | 0.141 [0.053–0.333] |
| very large (>= 10 kecamatan) | 18 (0.016) | sum | 0.839 [0.754–0.919] | 0.134 [0.053–0.315] |
| very large (>= 10 kecamatan) | 18 (0.016) | city | 0.816 [0.719–0.901] | 0.153 [0.046–0.377] |

Paired differences (95 %):

- any flood: sum - max ROC-AUC [-0.01, 0.007], PR-AUC [-0.017, 0.011]; city - max ROC-AUC [-0.025, 0.014], PR-AUC [-0.025, 0.041]; city - sum ROC-AUC [-0.022, 0.014], PR-AUC [-0.02, 0.042]
- large (>= 5 kecamatan): sum - max ROC-AUC [-0.006, 0.022], PR-AUC [-0.046, 0.013]; city - max ROC-AUC [-0.043, 0.031], PR-AUC [-0.128, 0.076]; city - sum ROC-AUC [-0.048, 0.022], PR-AUC [-0.109, 0.085]
- very large (>= 10 kecamatan): sum - max ROC-AUC [-0.018, 0.041], PR-AUC [-0.06, 0.025]; city - max ROC-AUC [-0.096, 0.063], PR-AUC [-0.172, 0.215]; city - sum ROC-AUC [-0.11, 0.055], PR-AUC [-0.146, 0.213]

| Label | Score | Alarms a month | Alarm days | Recall | Precision | Precision for any flood |
|---|---|---|---|---|---|---|
| large (>= 5 kecamatan) | max | 8 a month | 288 | 0.641 | 0.142 | 0.444 |
| large (>= 5 kecamatan) | max | 4 a month | 144 | 0.469 | 0.208 | 0.514 |
| large (>= 5 kecamatan) | max | 2 a month | 72 | 0.359 | 0.319 | 0.639 |
| large (>= 5 kecamatan) | max | 1 a month | 36 | 0.234 | 0.417 | 0.667 |
| large (>= 5 kecamatan) | sum | 8 a month | 288 | 0.688 | 0.153 | 0.448 |
| large (>= 5 kecamatan) | sum | 4 a month | 144 | 0.469 | 0.208 | 0.521 |
| large (>= 5 kecamatan) | sum | 2 a month | 72 | 0.297 | 0.264 | 0.569 |
| large (>= 5 kecamatan) | sum | 1 a month | 36 | 0.203 | 0.361 | 0.722 |
| large (>= 5 kecamatan) | city | 8 a month | 288 | 0.656 | 0.146 | 0.41 |
| large (>= 5 kecamatan) | city | 4 a month | 144 | 0.422 | 0.188 | 0.535 |
| large (>= 5 kecamatan) | city | 2 a month | 72 | 0.25 | 0.222 | 0.611 |
| large (>= 5 kecamatan) | city | 1 a month | 36 | 0.219 | 0.389 | 0.806 |
| very large (>= 10 kecamatan) | max | 8 a month | 288 | 0.722 | 0.045 | 0.444 |
| very large (>= 10 kecamatan) | max | 4 a month | 144 | 0.611 | 0.076 | 0.514 |
| very large (>= 10 kecamatan) | max | 2 a month | 72 | 0.389 | 0.097 | 0.639 |
| very large (>= 10 kecamatan) | max | 1 a month | 36 | 0.333 | 0.167 | 0.667 |
| very large (>= 10 kecamatan) | sum | 8 a month | 288 | 0.778 | 0.049 | 0.448 |
| very large (>= 10 kecamatan) | sum | 4 a month | 144 | 0.556 | 0.069 | 0.521 |
| very large (>= 10 kecamatan) | sum | 2 a month | 72 | 0.389 | 0.097 | 0.569 |
| very large (>= 10 kecamatan) | sum | 1 a month | 36 | 0.333 | 0.167 | 0.722 |
| very large (>= 10 kecamatan) | city | 8 a month | 288 | 0.722 | 0.045 | 0.41 |
| very large (>= 10 kecamatan) | city | 4 a month | 144 | 0.5 | 0.062 | 0.535 |
| very large (>= 10 kecamatan) | city | 2 a month | 72 | 0.278 | 0.069 | 0.611 |
| very large (>= 10 kecamatan) | city | 1 a month | 36 | 0.278 | 0.139 | 0.806 |

## lag 2 (rain through D-2) · 2016-2022 (complete labels) · 2557 days

| Label | Days (share) | Score | ROC-AUC [95 %] | PR-AUC [95 %] |
|---|---|---|---|---|
| any flood | 554 (0.217) | max | 0.671 [0.646–0.696] | 0.323 [0.292–0.36] |
| any flood | 554 (0.217) | sum | 0.672 [0.648–0.697] | 0.329 [0.297–0.368] |
| any flood | 554 (0.217) | city | 0.543 [0.517–0.572] | 0.268 [0.241–0.302] |
| large (>= 5 kecamatan) | 174 (0.068) | max | 0.703 [0.665–0.737] | 0.145 [0.112–0.189] |
| large (>= 5 kecamatan) | 174 (0.068) | sum | 0.699 [0.658–0.734] | 0.148 [0.114–0.192] |
| large (>= 5 kecamatan) | 174 (0.068) | city | 0.571 [0.525–0.623] | 0.116 [0.088–0.163] |
| very large (>= 10 kecamatan) | 65 (0.025) | max | 0.728 [0.672–0.783] | 0.074 [0.05–0.117] |
| very large (>= 10 kecamatan) | 65 (0.025) | sum | 0.733 [0.675–0.79] | 0.085 [0.055–0.135] |
| very large (>= 10 kecamatan) | 65 (0.025) | city | 0.618 [0.543–0.704] | 0.08 [0.046–0.159] |

Paired differences (95 %):

- any flood: sum - max ROC-AUC [-0.005, 0.008], PR-AUC [-0.004, 0.016]; city - max ROC-AUC [-0.162, -0.095], PR-AUC [-0.085, -0.024]; city - sum ROC-AUC [-0.158, -0.099], PR-AUC [-0.088, -0.034]
- large (>= 5 kecamatan): sum - max ROC-AUC [-0.015, 0.007], PR-AUC [-0.009, 0.015]; city - max ROC-AUC [-0.183, -0.079], PR-AUC [-0.062, 0.01]; city - sum ROC-AUC [-0.173, -0.078], PR-AUC [-0.061, 0.004]
- very large (>= 10 kecamatan): sum - max ROC-AUC [-0.01, 0.019], PR-AUC [-0.0, 0.027]; city - max ROC-AUC [-0.19, -0.029], PR-AUC [-0.032, 0.073]; city - sum ROC-AUC [-0.189, -0.036], PR-AUC [-0.041, 0.058]

| Label | Score | Alarms a month | Alarm days | Recall | Precision | Precision for any flood |
|---|---|---|---|---|---|---|
| large (>= 5 kecamatan) | max | 8 a month | 672 | 0.448 | 0.116 | 0.312 |
| large (>= 5 kecamatan) | max | 4 a month | 336 | 0.31 | 0.161 | 0.342 |
| large (>= 5 kecamatan) | max | 2 a month | 168 | 0.218 | 0.226 | 0.423 |
| large (>= 5 kecamatan) | max | 1 a month | 84 | 0.098 | 0.202 | 0.405 |
| large (>= 5 kecamatan) | sum | 8 a month | 672 | 0.489 | 0.126 | 0.323 |
| large (>= 5 kecamatan) | sum | 4 a month | 336 | 0.299 | 0.155 | 0.345 |
| large (>= 5 kecamatan) | sum | 2 a month | 168 | 0.19 | 0.196 | 0.393 |
| large (>= 5 kecamatan) | sum | 1 a month | 84 | 0.144 | 0.298 | 0.524 |
| large (>= 5 kecamatan) | city | 8 a month | 672 | 0.362 | 0.094 | 0.253 |
| large (>= 5 kecamatan) | city | 4 a month | 347 | 0.241 | 0.121 | 0.277 |
| large (>= 5 kecamatan) | city | 2 a month | 168 | 0.172 | 0.179 | 0.369 |
| large (>= 5 kecamatan) | city | 1 a month | 84 | 0.109 | 0.226 | 0.476 |
| very large (>= 10 kecamatan) | max | 8 a month | 672 | 0.523 | 0.051 | 0.312 |
| very large (>= 10 kecamatan) | max | 4 a month | 336 | 0.4 | 0.077 | 0.342 |
| very large (>= 10 kecamatan) | max | 2 a month | 168 | 0.308 | 0.119 | 0.423 |
| very large (>= 10 kecamatan) | max | 1 a month | 84 | 0.138 | 0.107 | 0.405 |
| very large (>= 10 kecamatan) | sum | 8 a month | 672 | 0.585 | 0.057 | 0.323 |
| very large (>= 10 kecamatan) | sum | 4 a month | 336 | 0.415 | 0.08 | 0.345 |
| very large (>= 10 kecamatan) | sum | 2 a month | 168 | 0.292 | 0.113 | 0.393 |
| very large (>= 10 kecamatan) | sum | 1 a month | 84 | 0.2 | 0.155 | 0.524 |
| very large (>= 10 kecamatan) | city | 8 a month | 672 | 0.431 | 0.042 | 0.253 |
| very large (>= 10 kecamatan) | city | 4 a month | 347 | 0.338 | 0.063 | 0.277 |
| very large (>= 10 kecamatan) | city | 2 a month | 168 | 0.262 | 0.101 | 0.369 |
| very large (>= 10 kecamatan) | city | 1 a month | 84 | 0.169 | 0.131 | 0.476 |

## lag 2 (rain through D-2) · 2023-2025 (partial labels) · 1096 days

| Label | Days (share) | Score | ROC-AUC [95 %] | PR-AUC [95 %] |
|---|---|---|---|---|
| any flood | 362 (0.33) | max | 0.6 [0.564–0.63] | 0.403 [0.361–0.451] |
| any flood | 362 (0.33) | sum | 0.603 [0.569–0.632] | 0.409 [0.364–0.456] |
| any flood | 362 (0.33) | city | 0.592 [0.557–0.624] | 0.39 [0.348–0.438] |
| large (>= 5 kecamatan) | 64 (0.058) | max | 0.733 [0.673–0.791] | 0.155 [0.104–0.241] |
| large (>= 5 kecamatan) | 64 (0.058) | sum | 0.727 [0.661–0.787] | 0.156 [0.103–0.241] |
| large (>= 5 kecamatan) | 64 (0.058) | city | 0.675 [0.606–0.739] | 0.135 [0.087–0.212] |
| very large (>= 10 kecamatan) | 18 (0.016) | max | 0.733 [0.624–0.841] | 0.061 [0.024–0.165] |
| very large (>= 10 kecamatan) | 18 (0.016) | sum | 0.717 [0.605–0.824] | 0.054 [0.021–0.145] |
| very large (>= 10 kecamatan) | 18 (0.016) | city | 0.739 [0.61–0.856] | 0.056 [0.026–0.144] |

Paired differences (95 %):

- any flood: sum - max ROC-AUC [-0.004, 0.01], PR-AUC [-0.004, 0.015]; city - max ROC-AUC [-0.031, 0.015], PR-AUC [-0.044, 0.018]; city - sum ROC-AUC [-0.035, 0.012], PR-AUC [-0.047, 0.01]
- large (>= 5 kecamatan): sum - max ROC-AUC [-0.019, 0.006], PR-AUC [-0.026, 0.019]; city - max ROC-AUC [-0.116, -0.003], PR-AUC [-0.105, 0.044]; city - sum ROC-AUC [-0.111, 0.008], PR-AUC [-0.098, 0.048]
- very large (>= 10 kecamatan): sum - max ROC-AUC [-0.042, 0.011], PR-AUC [-0.039, 0.014]; city - max ROC-AUC [-0.119, 0.132], PR-AUC [-0.107, 0.085]; city - sum ROC-AUC [-0.116, 0.158], PR-AUC [-0.087, 0.092]

| Label | Score | Alarms a month | Alarm days | Recall | Precision | Precision for any flood |
|---|---|---|---|---|---|---|
| large (>= 5 kecamatan) | max | 8 a month | 288 | 0.594 | 0.132 | 0.382 |
| large (>= 5 kecamatan) | max | 4 a month | 144 | 0.328 | 0.146 | 0.396 |
| large (>= 5 kecamatan) | max | 2 a month | 72 | 0.219 | 0.194 | 0.458 |
| large (>= 5 kecamatan) | max | 1 a month | 36 | 0.125 | 0.222 | 0.5 |
| large (>= 5 kecamatan) | sum | 8 a month | 288 | 0.516 | 0.115 | 0.399 |
| large (>= 5 kecamatan) | sum | 4 a month | 144 | 0.359 | 0.16 | 0.438 |
| large (>= 5 kecamatan) | sum | 2 a month | 72 | 0.203 | 0.181 | 0.417 |
| large (>= 5 kecamatan) | sum | 1 a month | 36 | 0.094 | 0.167 | 0.472 |
| large (>= 5 kecamatan) | city | 8 a month | 288 | 0.469 | 0.104 | 0.375 |
| large (>= 5 kecamatan) | city | 4 a month | 144 | 0.359 | 0.16 | 0.389 |
| large (>= 5 kecamatan) | city | 2 a month | 72 | 0.234 | 0.208 | 0.431 |
| large (>= 5 kecamatan) | city | 1 a month | 36 | 0.078 | 0.139 | 0.361 |
| very large (>= 10 kecamatan) | max | 8 a month | 288 | 0.611 | 0.038 | 0.382 |
| very large (>= 10 kecamatan) | max | 4 a month | 144 | 0.333 | 0.042 | 0.396 |
| very large (>= 10 kecamatan) | max | 2 a month | 72 | 0.278 | 0.069 | 0.458 |
| very large (>= 10 kecamatan) | max | 1 a month | 36 | 0.167 | 0.083 | 0.5 |
| very large (>= 10 kecamatan) | sum | 8 a month | 288 | 0.444 | 0.028 | 0.399 |
| very large (>= 10 kecamatan) | sum | 4 a month | 144 | 0.333 | 0.042 | 0.438 |
| very large (>= 10 kecamatan) | sum | 2 a month | 72 | 0.222 | 0.056 | 0.417 |
| very large (>= 10 kecamatan) | sum | 1 a month | 36 | 0.167 | 0.083 | 0.472 |
| very large (>= 10 kecamatan) | city | 8 a month | 288 | 0.667 | 0.042 | 0.375 |
| very large (>= 10 kecamatan) | city | 4 a month | 144 | 0.444 | 0.056 | 0.389 |
| very large (>= 10 kecamatan) | city | 2 a month | 72 | 0.278 | 0.069 | 0.431 |
| very large (>= 10 kecamatan) | city | 1 a month | 36 | 0.111 | 0.056 | 0.361 |

