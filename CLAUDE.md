# FloodAI

FastAPI backend + React frontend. Agentic flood prediction system for Jakarta.

## Stack
- Backend: FastAPI + uvicorn, port 8080
- Frontend: React + Vite
- DB: Supabase/PostgreSQL (RPC over HTTPS via `supabase` client; psycopg2 for direct/pooled access)
- ML: XGBoost + scikit-learn 1.8.0; plus a Torch `realtime_native` model
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
- Calibration step deactivated (ECE 0.3784).
- BNPB district mapping gap (kecamatan write-back); InaRISK falls back to bundled static JSON.

## Resolved
- DB CHECK-constraint naming drift (orphan `chk_eval_status` blocked `CONFLICT`/`LOW_TRUST`
  persistence) — fixed by `db/migrations/106_fix_status_constraint_naming_drift.sql`, applied
  to Supabase 2026-06-19.
