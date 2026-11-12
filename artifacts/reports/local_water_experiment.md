# City-wide or per-post water levels in the daily model

Generated 2026-11-12T01:04:36+00:00 by `scripts/local_water_experiment.py` on cuda. Nothing here is served.

Kecamatan-days with water levels, test years 2019–2021 pooled: 33138 rows, 771 floods (prevalence 0.0233). Per-post features: KATULAMPA, DEPOK, MANGGARAI, KARET, KRUKUTHULU, PESANGGRAHAN, ANGKEHULU, SUNTERHULU, CIPINANGHULU, PULOGADUNG, MARINAANCOL, PASARIKAN.

| Variant | ROC-AUC [95 %] | PR-AUC [95 %] |
|---|---|---|
| V0 F4 | 0.778 [0.749–0.806] | 0.078 [0.059–0.105] |
| V1 + city water | 0.81 [0.784–0.837] | 0.131 [0.097–0.182] |
| V2 + city water + per post + location | 0.81 [0.784–0.835] | 0.136 [0.095–0.186] |
| V3 + per post + location | 0.796 [0.77–0.822] | 0.124 [0.091–0.166] |
| A0 day ahead | 0.741 [0.707–0.777] | 0.068 [0.049–0.096] |
| A1 day ahead + yesterday's water + location | 0.747 [0.718–0.778] | 0.072 [0.053–0.104] |

| Paired difference (95 %) | ROC-AUC | PR-AUC |
|---|---|---|
| V1 + city water minus V0 F4 | [0.02, 0.046] | [0.032, 0.084] |
| V2 + city water + per post + location minus V1 + city water | [-0.013, 0.012] | [-0.023, 0.027] |
| V3 + per post + location minus V1 + city water | [-0.028, -0.0] | [-0.04, 0.015] |
| A1 day ahead + yesterday's water + location minus A0 day ahead | [-0.011, 0.023] | [-0.013, 0.024] |

ROC-AUC by test year:

| Year | Floods | V0 F4 | V1 + city water | V2 + city water + per post + location | V3 + per post + location | A0 day ahead | A1 day ahead + yesterday's water + location |
|---|---|---|---|---|---|---|---|
| 2019 | 126 | 0.883 | 0.899 | 0.893 | 0.882 | 0.855 | 0.872 |
| 2020 | 560 | 0.752 | 0.789 | 0.798 | 0.776 | 0.704 | 0.716 |
| 2021 | 85 | 0.866 | 0.896 | 0.913 | 0.935 | 0.804 | 0.826 |

Run time 147.5 s.
