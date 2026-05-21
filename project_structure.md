# Dewa AI (FloodAI) — Project Structure

> **Reorganization verdict:** the repository was already organized as a clean,
> import-stable FastAPI package rooted at `app/`. The generic "flatten into
> top-level `api/ agents/ models/ config/ utils/ scrapers/`" mapping was **not**
> applied because it would break every `from app.* import …` (~60 source files,
> ~50 test files), the `uvicorn app.api.main:app` entrypoint, `pyproject.toml`
> packaging, and `vercel.json`. `reorganize.sh` therefore performs **safe
> cleanup only** and leaves the package layout intact.

## Directory Tree
```
FloodAI/
├── app/                          # Python package root (import base: `app.`)
│   ├── api/                      # FastAPI: main.py, security.py, observability.py
│   │   └── routes/               # agentic_llm.py
│   ├── agents/                   # perception/reasoning/evaluation/action/routing + llm_orchestrator
│   ├── services/                 # business logic, locators, fetchers, scrapers
│   │   ├── data_ingestion/       # tma_scraper.py
│   │   └── routing/              # route_planner.py
│   ├── core/                     # decision_core, enums, output_contract
│   ├── domain/                   # decision.py (pure decision rules)
│   ├── pipeline/                 # flood_pipeline.py (Perception→…→Action orchestration)
│   ├── realtime_native/          # XGBoost inference: bundle, feature_builder, inference, training
│   ├── evaluation/               # calibration, metrics, scenario_runner, historical_*
│   ├── monitoring/               # drift_monitor.py
│   ├── config/                   # llm_config.py
│   ├── contracts/                # vocabulary.py
│   ├── utils/                    # paths.py
│   └── data/                     # bundled runtime JSON (shelters, pumps, hazard index, …)
├── db/                           # psycopg2_connection, pipeline_writer, repositories/
│   └── migrations/               # 000…105 SQL migrations
├── models/                       # ML artifacts: *.pkl, thresholds, SHAP png, realtime_native_bundle/
├── data/                         # raw/ (source XLS/CSV/GeoJSON) · processed/ · external/
├── demnas/                       # DEMNAS *.tif elevation rasters
├── scripts/                      # build_*.py data builders, migrate/ingest/verify utilities
├── tests/                        # 90+ tests (root, unit/, integration/)
├── poskobanjir/                  # standalone fetcher (BMKG/OpenWeather/posko XML)
├── frontend/                     # Vite + React SPA (src/App.jsx, styles.css)
├── docs/guides/                  # design + runbook docs
├── artifacts/                    # generated reports/visualizations (output)
├── notebooks/                    # production/jakarta_flood_prediction.ipynb
├── skills/                       # reference skill notes
├── _archive/                     # quarantined non-source (e.g. get-pip.py)
├── pyproject.toml · requirements.txt · README.md
├── vercel.json · .env.example · .dockerignore · .gitignore
└── reorganize.sh · project_structure.md
```

## Folder Descriptions
| Folder | Contents | Approx. files |
|---|---|---|
| `app/api/` (+`routes/`) | FastAPI app, endpoints, security, observability | 7 |
| `app/agents/` | 5 pipeline agents + LLM orchestrator | 7 |
| `app/services/` (+`data_ingestion/`,`routing/`) | locators, fetchers, decision/hydrology/bnpb logic, scrapers | ~40 |
| `app/core/`,`app/domain/` | canonical decision logic, enums, output contract | 7 |
| `app/pipeline/` | single-entry pipeline orchestration | 2 |
| `app/realtime_native/` | XGBoost bundle load + inference + training | 5 |
| `app/evaluation/`,`app/monitoring/` | calibration/metrics/scenarios, drift monitoring | 8 |
| `app/config/`,`app/contracts/`,`app/utils/` | config, vocabulary, path helpers | 6 |
| `app/data/` | bundled runtime JSON datasets | 17 |
| `db/` (+`migrations/`,`repositories/`) | Postgres access + 30+ SQL migrations | ~40 |
| `models/` (+`realtime_native_bundle/`) | `.pkl` models, thresholds, SHAP plots | ~35 |
| `data/raw`,`data/processed`,`data/external` | source + cleaned datasets | ~50 |
| `demnas/` | DEMNAS GeoTIFF elevation rasters (`.tif`) | 3 |
| `scripts/` | data builders + DB/ingest/verify utilities | ~20 |
| `tests/` (+`unit/`,`integration/`) | pytest suites | ~50 |
| `poskobanjir/` | standalone external-data fetcher service | ~10 |
| `frontend/` | Vite/React operator UI | ~7 |

## Deleted / Archived Files (by `reorganize.sh`)
| File / Folder | Action | Reason |
|---|---|---|
| `**/__pycache__/`, `*.pyc`, `*.pyo` | delete | Compiled bytecode (regenerated) |
| `.pytest_cache/` | delete | Test cache (regenerated) |
| `temp_index_html.txt` | delete | `temp_*` scratch dump |
| `server_log.txt` | delete | Stray runtime log |
| `poskobanjir/logs/log.txt` | delete | Stray runtime log |
| `data/raw/…luapan-sungai-…data (1).xls` | delete | Byte-identical duplicate (same md5 as the non-`(1)` file) |
| `get-pip.py` | move → `_archive/` | Vendored bootstrap, not project source (`.py`, so archived not deleted) |

**Intentionally NOT deleted** (per constraints / safety):
- `.env`, `app/.env`, `.env.example` — environment/config (never delete). Note: `.env` still holds live secrets and remains git-tracked — rotating + gitignoring it is a separate security follow-up.
- `_deprecated/README.md` — README (never delete).
- All `.py`, `.pkl`, `.tif`, `requirements.txt`, `README*` — protected.

## Migration Notes
- **No source files were moved**, so there are **no broken import paths** to fix.
  The entrypoint stays `uvicorn app.api.main:app`; `pyproject.toml` / `vercel.json` unchanged.
- `reorganize.sh` is **not run automatically** — review and run it yourself
  (`bash reorganize.sh`), then verify with `git status --short`.
- If you genuinely want the literal top-level flatten (`api/`, `agents/`,
  `models/`, `config/`, `utils/`, `scrapers/`): that is a large, breaking
  refactor requiring a full rewrite of `app.*` imports across ~110 files plus
  entrypoint/packaging/deploy config. It should be done as a dedicated branch
  with the test suite as the safety net — not via a blind `mv` script. Say the
  word and I'll plan it properly.
