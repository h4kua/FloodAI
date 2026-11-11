# Daily flood model, 2013 to Sep 2025, tested year by year

Generated 2026-11-10T17:59:46+00:00 by `scripts/long_experiments.py` on cuda. Nothing here is served.

195552 kecamatan-days. Each test year is scored by models trained on every earlier year only. BPBD flood dates are complete to 2022 and partly readable for 2023–2025.

Flood kecamatan-days by year: 2013: 374, 2014: 671, 2015: 224, 2016: 407, 2017: 239, 2018: 151, 2019: 145, 2020: 704, 2021: 323, 2022: 544, 2023: 213, 2024: 424, 2025: 353.

## Pooled test years 2016–2022 (complete labels)

107394 rows, 2513 flood rows (prevalence 0.0234, the no-skill PR-AUC).

| Model | ROC-AUC [95 %] | PR-AUC [95 %] |
|---|---|---|
| baseline: rain that day | 0.75 [0.721–0.778] | 0.093 [0.066–0.14] |
| logistic F4 | 0.821 [0.801–0.842] | 0.142 [0.107–0.193] |
| XGBoost F4 | 0.841 [0.822–0.859] | 0.146 [0.113–0.192] |
| XGBoost F5 (+ hourly intensity) | 0.844 [0.826–0.861] | 0.148 [0.113–0.2] |
| XGBoost F6 (+ drivers) | 0.839 [0.82–0.856] | 0.153 [0.119–0.198] |
| day ahead, no drivers | 0.82 [0.802–0.837] | 0.111 [0.09–0.138] |
| day ahead, + drivers | 0.816 [0.797–0.834] | 0.119 [0.094–0.151] |

| Paired difference (95 %) | ROC-AUC | PR-AUC |
|---|---|---|
| XGBoost F4 minus baseline: rain that day | [0.067, 0.114] | [0.023, 0.081] |
| XGBoost F4 minus logistic F4 | [0.011, 0.03] | [-0.015, 0.022] |
| XGBoost F5 (+ hourly intensity) minus XGBoost F4 | [-0.001, 0.006] | [-0.006, 0.011] |
| XGBoost F6 (+ drivers) minus XGBoost F5 (+ hourly intensity) | [-0.015, 0.004] | [-0.016, 0.022] |
| day ahead, + drivers minus day ahead, no drivers | [-0.016, 0.008] | [-0.005, 0.023] |

## Pooled test years 2023–Sep 2025 (partial labels)

42168 rows, 990 flood rows (prevalence 0.0235, the no-skill PR-AUC).

| Model | ROC-AUC [95 %] | PR-AUC [95 %] |
|---|---|---|
| baseline: rain that day | 0.743 [0.711–0.77] | 0.082 [0.057–0.114] |
| logistic F4 | 0.828 [0.807–0.847] | 0.181 [0.13–0.234] |
| XGBoost F4 | 0.869 [0.852–0.884] | 0.178 [0.132–0.227] |
| XGBoost F5 (+ hourly intensity) | 0.868 [0.851–0.884] | 0.192 [0.142–0.248] |
| XGBoost F6 (+ drivers) | 0.872 [0.855–0.887] | 0.188 [0.139–0.242] |
| day ahead, no drivers | 0.836 [0.817–0.853] | 0.121 [0.09–0.162] |
| day ahead, + drivers | 0.841 [0.822–0.859] | 0.13 [0.093–0.173] |

| Paired difference (95 %) | ROC-AUC | PR-AUC |
|---|---|---|
| XGBoost F4 minus baseline: rain that day | [0.104, 0.15] | [0.063, 0.134] |
| XGBoost F4 minus logistic F4 | [0.029, 0.053] | [-0.033, 0.026] |
| XGBoost F5 (+ hourly intensity) minus XGBoost F4 | [-0.006, 0.004] | [-0.002, 0.034] |
| XGBoost F6 (+ drivers) minus XGBoost F5 (+ hourly intensity) | [-0.006, 0.014] | [-0.034, 0.022] |
| day ahead, + drivers minus day ahead, no drivers | [-0.006, 0.015] | [-0.012, 0.027] |

## ROC-AUC by test year

| Year | Floods | baseline: rain that day | logistic F4 | XGBoost F4 | XGBoost F5 (+ hourly intensity) | XGBoost F6 (+ drivers) | day ahead, no drivers | day ahead, + drivers |
|---|---|---|---|---|---|---|---|---|
| 2016 | 407 | 0.706 | 0.79 | 0.801 | 0.811 | 0.825 | 0.794 | 0.804 |
| 2017 | 239 | 0.728 | 0.869 | 0.865 | 0.87 | 0.878 | 0.858 | 0.872 |
| 2018 | 151 | 0.83 | 0.87 | 0.885 | 0.887 | 0.816 | 0.852 | 0.783 |
| 2019 | 145 | 0.873 | 0.915 | 0.919 | 0.914 | 0.915 | 0.888 | 0.889 |
| 2020 | 704 | 0.785 | 0.785 | 0.815 | 0.82 | 0.824 | 0.784 | 0.793 |
| 2021 | 323 | 0.777 | 0.858 | 0.866 | 0.868 | 0.861 | 0.842 | 0.832 |
| 2022 | 544 | 0.597 | 0.734 | 0.786 | 0.781 | 0.782 | 0.751 | 0.76 |
| 2023 | 213 | 0.848 | 0.892 | 0.918 | 0.915 | 0.915 | 0.893 | 0.89 |
| 2024 | 424 | 0.709 | 0.778 | 0.822 | 0.826 | 0.827 | 0.794 | 0.792 |
| 2025 | 353 | 0.677 | 0.821 | 0.871 | 0.869 | 0.886 | 0.823 | 0.851 |

## PR-AUC by test year

| Year | Prevalence | baseline: rain that day | logistic F4 | XGBoost F4 | XGBoost F5 (+ hourly intensity) | XGBoost F6 (+ drivers) | day ahead, no drivers | day ahead, + drivers |
|---|---|---|---|---|---|---|---|---|
| 2016 | 0.0265 | 0.073 | 0.173 | 0.193 | 0.19 | 0.17 | 0.168 | 0.167 |
| 2017 | 0.0156 | 0.08 | 0.156 | 0.156 | 0.17 | 0.221 | 0.2 | 0.265 |
| 2018 | 0.0098 | 0.041 | 0.054 | 0.085 | 0.085 | 0.071 | 0.061 | 0.044 |
| 2019 | 0.0095 | 0.11 | 0.095 | 0.089 | 0.075 | 0.077 | 0.073 | 0.066 |
| 2020 | 0.0458 | 0.23 | 0.19 | 0.171 | 0.189 | 0.221 | 0.129 | 0.151 |
| 2021 | 0.0211 | 0.092 | 0.236 | 0.226 | 0.213 | 0.202 | 0.129 | 0.135 |
| 2022 | 0.0355 | 0.063 | 0.097 | 0.106 | 0.099 | 0.101 | 0.085 | 0.085 |
| 2023 | 0.0139 | 0.067 | 0.141 | 0.197 | 0.183 | 0.223 | 0.148 | 0.187 |
| 2024 | 0.0276 | 0.068 | 0.123 | 0.152 | 0.156 | 0.131 | 0.11 | 0.09 |
| 2025 | 0.0308 | 0.117 | 0.267 | 0.201 | 0.246 | 0.235 | 0.125 | 0.15 |

Missing values (share of rows): d7prev 0.0002, hist_rate 0.0784.

Run time 911.3 s.
