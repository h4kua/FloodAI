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
  the current realtime-native bundle: 0.062 (`artifacts/reports/model_evaluation.md`) is its
  bootstrap-proxy random test split and optimistic (the 0.0183 in `training_stats.json` came from an
  ECE function that mixed quantile and equal-width bins, fixed 2026-10-24); 0.1962 (`artifacts/configurations/calibration_cache.json`,
  labels derived from the model's own ranking) and 0.3784 (`artifacts/reports/scenario_validation.json`,
  n=7) come from older model versions.
- Bundle retrained 2026-10-23 (`scripts/retrain_bundle.py`) with the leak-free
  `kecamatan_historical_flood_freq` (per row, events from earlier years only; inference uses
  years before the snapshot's year). Test AUC 0.904 / recall 0.893 / precision 0.263 /
  threshold 0.103 (was 0.036). The previous bundle stays in git history (d06dc0c and earlier).
- The split is still a RANDOM stratified 68/12/20 (train 1990 / val 352 / test 586, 56 test
  positives): the chronological validation slice (May 2023–Jan 2024) has 0 positives, so training
  falls back to random (the report now says so). Test rows are spread over 2020–2024, so the
  metrics above are optimistic. By-year estimate (train 2020–2022, val 2023, test 2024 with 22
  positives): AUC 0.81 [0.74–0.87], PR-AUC 0.10 (no-skill 0.04), ECE 0.19. Run
  `python scripts/evaluate_model.py` for the current figures with 95 % bootstrap CIs.
  Flood labels shrink sharply over time (117/78/54/11/22, 2020–2024).
- No observed row-level flood labels for evaluation: `realtime_feature_history.csv` has no label
  column; `calibration_labeled.csv` labels are synthetic.
- AUC 0.9452 belongs to the legacy Jakarta model (`flood_model_jakarta.pkl`, random 80:20 split).
  Its endpoint `/predict/realtime` was retired 2026-10-24 (410 Gone); the UI uses `/predict/realtime-native`.
- BNPB district mapping gap (kecamatan write-back); InaRISK falls back to bundled static JSON.

## Resolved
- 2026-10-24: served model = trained model. The native export kept only fold 0's booster and
  applied all five calibrators to it (per-prediction gap up to 0.32); it now ships one booster per
  calibration fold (`xgboost_model_fold{i}.json`), parity < 1e-6. Calibration method is chosen on
  the validation fold (was the test fold); threshold selection no longer returns 1.0 (recall 0) when
  no threshold reaches the precision floor.
- 2026-10-24: `POST /api/chat` rate-limited per IP (`FLOOD_CHAT_RATE_LIMIT`, Fly client IP from
  `Fly-Client-IP`); `/reports`, `/sos`, `/family/*` off unless `COMMUNITY_API_ENABLED=true`;
  CI in `.github/workflows/ci.yml` (pytest + frontend build).
- DB CHECK-constraint naming drift (orphan `chk_eval_status` blocked `CONFLICT`/`LOW_TRUST`
  persistence) — fixed by `db/migrations/106_fix_status_constraint_naming_drift.sql`, applied
  to Supabase 2026-06-19.
