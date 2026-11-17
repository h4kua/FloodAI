# Experiments on the learned decision layer

Generated 2026-11-17T13:13:24+00:00 by `scripts/decision_layer_experiments.py` on cuda (1000 day resamples). Rain lag 1. Test years 2019, 2020, 2021, 2025: 3090 snapshots on 1062 days, flood days 0.221. Nothing here changes the site.

Levels read as alarm share / recall / precision.

## 1 and 3 · Inputs: today's rain, and what each input adds

Rules (river posts + daily Waspada): ROC-AUC 0.694 [0.663–0.723]; Waspada 0.269/0.558/0.458 · Siaga 0.039/0.129/0.727 · Bahaya 0.015/0.051/0.761.

| Variant | ROC-AUC [95 %] | − served, 95 % | Levels | Recall − served (95 %) per level |
|---|---|---|---|---|
| served (daily chance + posts now + yesterday) | 0.775 [0.735–0.811] | [0.0, 0.0] | Waspada 0.443/0.758/0.378 · Siaga 0.052/0.174/0.739 · Bahaya 0.024/0.082/0.767 | Waspada [0.0, 0.0] · Siaga [0.0, 0.0] · Bahaya [0.0, 0.0] |
| + today's rain so far (and the hour) | 0.786 [0.748–0.821] | [-0.01, 0.033] | Waspada 0.359/0.691/0.426 · Siaga 0.064/0.22/0.758 · Bahaya 0.031/0.117/0.842 | Waspada [-0.11, -0.024] · Siaga [0.006, 0.085] · Bahaya [0.01, 0.064] |
| without the daily model | 0.739 [0.694–0.779] | [-0.054, -0.02] | Waspada 0.364/0.644/0.391 · Siaga 0.049/0.163/0.74 · Bahaya 0.025/0.088/0.779 | Waspada [-0.156, -0.075] · Siaga [-0.035, 0.008] · Bahaya [0.001, 0.012] |
| without yesterday's posts | 0.758 [0.722–0.792] | [-0.038, 0.005] | Waspada 0.527/0.81/0.339 · Siaga 0.069/0.205/0.66 · Bahaya 0.023/0.078/0.746 | Waspada [0.003, 0.102] · Siaga [0.002, 0.06] · Bahaya [-0.018, 0.008] |
| without the upstream posts | 0.768 [0.727–0.805] | [-0.012, -0.003] | Waspada 0.457/0.76/0.368 · Siaga 0.058/0.177/0.676 · Bahaya 0.021/0.075/0.773 | Waspada [-0.007, 0.011] · Siaga [-0.021, 0.027] · Bahaya [-0.02, 0.004] |
| daily model alone | 0.723 [0.687–0.763] | [-0.077, -0.023] | Waspada 0.561/0.776/0.306 · Siaga 0.019/0.066/0.776 · Bahaya 0.015/0.051/0.761 | Waspada [-0.038, 0.074] · Siaga [-0.143, -0.074] · Bahaya [-0.046, -0.017] |
| posts now alone | 0.621 [0.58–0.66] | [-0.191, -0.118] | Waspada 0.5/0.52/0.23 · Siaga 0.084/0.24/0.633 · Bahaya 0.024/0.089/0.813 | Waspada [-0.3, -0.173] · Siaga [0.034, 0.1] · Bahaya [-0.008, 0.022] |

## 3 · Calibration of the served chance

ECE 0.0745, Brier 0.1493 (no skill 0.1722). ECE by test year: {'2019': 0.0505, '2020': 0.1803, '2021': 0.0575, '2025': 0.17}.

| Chance | Snapshots | Mean chance | Flood share |
|---|---|---|---|
| 0-10 % | 1531 | 0.038 | 0.072 |
| 10-20 % | 732 | 0.136 | 0.265 |
| 20-30 % | 383 | 0.238 | 0.352 |
| 30-40 % | 211 | 0.344 | 0.469 |
| 40-50 % | 54 | 0.435 | 0.574 |
| 50-60 % | 92 | 0.543 | 0.565 |
| 60-70 % | 40 | 0.639 | 0.575 |
| 70-80 % | 27 | 0.759 | 0.778 |
| 80-90 % | 17 | 0.853 | 0.882 |
| 90-100 % | 3 | 0.911 | 1.0 |

## 3 · Waspada threshold (served chance, test snapshots)

| Threshold | Alarm share | Recall | Precision |
|---|---|---|---|
| 0.1 | 0.505 | 0.839 | 0.368 |
| 0.125 | 0.395 | 0.726 | 0.407 |
| 0.15 | 0.355 | 0.671 | 0.418 |
| 0.175 | 0.289 | 0.59 | 0.451 |
| 0.2 | 0.268 | 0.555 | 0.458 |
| 0.225 | 0.215 | 0.467 | 0.48 |
| 0.25 | 0.184 | 0.417 | 0.501 |
| 0.275 | 0.161 | 0.376 | 0.515 |
| 0.3 | 0.144 | 0.357 | 0.55 |
| 0.325 | 0.119 | 0.324 | 0.602 |
| 0.35 | 0.11 | 0.293 | 0.587 |
| 0.375 | 0.083 | 0.234 | 0.623 |
| 0.4 | 0.075 | 0.212 | 0.622 |
| 0.425 | 0.065 | 0.184 | 0.627 |
| 0.45 | 0.063 | 0.18 | 0.628 |
| 0.475 | 0.061 | 0.176 | 0.635 |
| 0.5 | 0.058 | 0.167 | 0.637 |

## 2 · One status per wilayah

15450 wilayah-snapshots, a flood in the wilayah on 0.084 of them.

- City level for every wilayah: ROC-AUC 0.762 [0.725–0.795]; Waspada 0.443/0.802/0.153 · Siaga 0.052/0.218/0.354 · Bahaya 0.024/0.109/0.389.
- Own wilayah layer: ROC-AUC 0.803 [0.772–0.829] (− city [0.026, 0.057]); Waspada 0.568/0.908/0.135 · Siaga 0.056/0.297/0.449 · Bahaya 0.026/0.166/0.534.
- Own − city per level: Waspada recall [0.07, 0.15], precision [-0.028, -0.008] · Siaga recall [0.043, 0.119], precision [0.046, 0.142] · Bahaya recall [0.025, 0.092], precision [0.069, 0.225]

| Wilayah | Flood share | City: Waspada / Siaga recall, precision | Own: Waspada / Siaga recall, precision |
|---|---|---|---|
| Jakarta Barat | 0.091 | 0.826, 0.17 / 0.238, 0.416 | 0.929, 0.122 / 0.291, 0.429 |
| Jakarta Pusat | 0.016 | 0.78, 0.028 / 0.34, 0.106 | 0.56, 0.086 / 0.14, 0.269 |
| Jakarta Selatan | 0.117 | 0.843, 0.224 / 0.229, 0.516 | 0.953, 0.156 / 0.344, 0.5 |
| Jakarta Timur | 0.118 | 0.844, 0.226 / 0.251, 0.571 | 1.0, 0.132 / 0.423, 0.483 |
| Jakarta Utara | 0.079 | 0.652, 0.116 / 0.107, 0.161 | 0.75, 0.141 / 0.078, 0.247 |

## 5 · Lead time before the first news report (2020-2021)

46 flood days with a BPBD record and a detik.com report; first report at 12.0 h WIB (median).

- >= Waspada before the first report: rules 0.826 (median lead 13.1 h, >= 6 h on 0.674), learned 0.848 (median 16.7 h, >= 6 h on 0.717); learned − rules [-0.065, 0.109].
- >= Siaga before the first report: rules 0.217 (median lead 6.1 h, >= 6 h on 0.13), learned 0.304 (median 7.3 h, >= 6 h on 0.239); learned − rules [-0.022, 0.217].
