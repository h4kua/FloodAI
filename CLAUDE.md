# FloodAI

FastAPI backend + React frontend. Agentic flood prediction system for Jakarta.

## Stack
- Backend: FastAPI + uvicorn, port 8080
- Frontend: React + Vite
- DB: Supabase/PostgreSQL (RPC over HTTPS via `supabase` client; psycopg2 for direct/pooled access)
- ML: XGBoost + scikit-learn 1.8.0 — the `realtime_native` bundle (`models/realtime_native_bundle/`)
  serves the UI; the legacy Jakarta model serves only `/predict/realtime`. No Torch.
- LLM (non-critical path): Groq (LLaMA-3) primary, Anthropic Claude optional — explanation only
- Deploy: Fly.io (backend, `fly.toml`) + Vercel (frontend, `vercel.json`)

## Run
```
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
```

## Architecture
5-stage agentic pipeline (`pipeline/flood_pipeline.py`):
Perception → Reasoning (XGBoost + OOD) → Evaluation (decision engine L0–L4) → Action → Routing.
The LLM is NOT in the critical path — decisions are deterministic; the LLM only generates the
Bahasa Indonesia explanation and falls back to a static template on failure.

## Key paths
- API: `api/main.py`
- Agentic pipeline: `pipeline/flood_pipeline.py`
- Decision engine: `services/decision_engine.py` (the former `app/` package was flattened)
- Output contract / canonical enums: `core/output_contract.py`, `contracts/vocabulary.py`
- Tests: `tests/`

## Data ingestion
- Live water levels: Jakarta Satu ArcGIS FeatureServers via `services/pintu_air_fetcher.py`
  + `services/awlr_threshold_fetcher.py` (clean JSON, no browser). Refresh: `scripts/run_tma_scraper.py`.
- The legacy TMA scraping-proxy + Selenium DOM scrape (`services/data_ingestion/tma_scraper.py`)
  is intentionally DISABLED (no `TMA_PROXY_URL`); it degrades to STALE, never crashes.
- Weather/alerts: OpenWeather + BMKG.

## Known issues
- Calibration penalty deactivated (`services/decision_engine.py`). No valid field ECE exists for
  the current realtime-native bundle: 0.0138 (`models/realtime_native_bundle/training_stats.json`)
  is its bootstrap-proxy test split and optimistic; 0.1962 (`artifacts/configurations/calibration_cache.json`,
  labels derived from the model's own ranking) and 0.3784 (`artifacts/reports/scenario_validation.json`,
  n=7) come from older model versions.
- Target leakage: `kecamatan_historical_flood_freq` is built from BPBD events 2020–2026
  (`data/bundled/kelurahan_flood_history.json`), which includes the 2024 test period, so the
  bundle's test metrics (AUC 0.901, recall 0.839) are inflated.
- The split named `chronological_80_15_5` is actually 68/12/20 (train 1990 / val 352 / test 586).
- No observed row-level flood labels for evaluation: `realtime_feature_history.csv` has no label
  column; `calibration_labeled.csv` labels are synthetic.
- AUC 0.9452 belongs to the legacy Jakarta model (`flood_model_jakarta.pkl`, random 80:20 split),
  served only by `/predict/realtime`; the UI uses `/predict/realtime-native`.
- BNPB district mapping gap (kecamatan write-back); InaRISK falls back to bundled static JSON.

## Resolved
- DB CHECK-constraint naming drift (orphan `chk_eval_status` blocked `CONFLICT`/`LOW_TRUST`
  persistence) — fixed by `db/migrations/106_fix_status_constraint_naming_drift.sql`, applied
  to Supabase 2026-06-19.
