# News-derived flood days for 2023–2025

Generated 2026-11-12T07:31:20+00:00 by `scripts/news_label_experiment.py` on cuda. Nothing here is served.

## Checks of the news source

- 2020-2022 (complete BPBD dates): news kecamatan days 1022, inside a bpbd flood month 825, filtered confirmed within 1 day 602, filtered 825, all confirmed within 1 day 602.
- 2023-2025: news kecamatan days 1208, inside a bpbd flood month 860, near a dated bpbd day 577.

## Flood kecamatan-days per test year

| Year | BPBD dated | BPBD + news |
|---|---|---|
| 2023 | 213 | 297 |
| 2024 | 424 | 587 |
| 2025 | 353 | 426 |

## Test years 2023 to Sep 2025 (rolling models)

| Model · labels scored | Floods | ROC-AUC [95 %] | PR-AUC [95 %] | Recall / precision at 1 alarm per kecamatan-month |
|---|---|---|---|---|
| trained on bpbd | scored on bpbd | 990 | 0.869 [0.852–0.884] | 0.178 [0.132–0.227] | 0.273 / 0.195 |
| trained on bpbd | scored on bpbd+news | 1310 | 0.873 [0.857–0.887] | 0.216 [0.171–0.268] | 0.276 / 0.261 |
| trained on bpbd+news | scored on bpbd | 990 | 0.865 [0.848–0.881] | 0.178 [0.132–0.23] | 0.286 / 0.204 |
| trained on bpbd+news | scored on bpbd+news | 1310 | 0.869 [0.853–0.884] | 0.214 [0.168–0.267] | 0.283 / 0.268 |

- News days are kept only inside a kecamatan-month that BPBD recorded as flooded.
- The 1-alarm threshold is the model's own top 3.3 % of kecamatan-days in the test years.
