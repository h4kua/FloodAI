# Driver ablation

Generated 2026-11-10T14:04:46+00:00 by `scripts/driver_ablation.py`. Each group is added on its own to F4; XGBoost (default settings) trained 2020–2021, validated 2022, tested 2023 to Sep 2025.

F4 alone: PR-AUC on 2022 0.116, test ROC-AUC 0.834, test PR-AUC 0.147.

| Added to F4 | PR-AUC on 2022 | Test ROC-AUC | Test PR-AUC | ROC-AUC vs F4 (95 %) | PR-AUC vs F4 (95 %) |
|---|---|---|---|---|---|
| hourly rain intensity | 0.112 | 0.838 | 0.177 | [-0.006, 0.012] | [0.01, 0.048] |
| soil moisture (ERA5-Land, day before) | 0.113 | 0.832 | 0.136 | [-0.006, 0.003] | [-0.027, 0.003] |
| MJO (OMI index) | 0.1 | 0.832 | 0.16 | [-0.013, 0.009] | [-0.013, 0.038] |
| ENSO (ONI) | 0.115 | 0.84 | 0.159 | [0.002, 0.011] | [-0.005, 0.029] |
| northerly surge (wind from the north, Java Sea) | 0.112 | 0.837 | 0.143 | [-0.004, 0.011] | [-0.029, 0.018] |
| spring tide (moon phase) on the coast | 0.124 | 0.837 | 0.15 | [-0.005, 0.011] | [-0.016, 0.026] |

- An interval that excludes 0 on the test years and a higher PR-AUC on 2022 = a robust gain.

## Day ahead (no rain of the day itself)

Features: d1, d3prev, d7prev, api14, up_bogor_d1, hist_rate, month_sin, month_cos, elevation, slope; drivers: soil07_prev, soil728_prev, mjo_x, mjo_y, mjo_amp, oni, north_wind_d1, spring_tide, coastal, coastal_spring_tide.

| Model | PR-AUC on 2022 | Test ROC-AUC | Test PR-AUC |
|---|---|---|---|
| without drivers | 0.084 | 0.78 | 0.069 |
| with drivers | 0.077 | 0.8 | 0.088 |

With minus without (95 %): ROC-AUC [0.001, 0.041], PR-AUC [0.001, 0.039].
