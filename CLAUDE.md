# FloodAI

FastAPI backend + React frontend. Agentic flood prediction system for Jakarta.

## Stack
- Backend: FastAPI + uvicorn, port 8080
- Frontend: React + Vite
- DB: Supabase/PostgreSQL (RPC over HTTPS via `supabase` client; psycopg2 for direct/pooled access)
- ML: XGBoost + scikit-learn 1.8.0 — the `realtime_native` bundle (`models/realtime_native_bundle/`)
  serves the UI; the legacy Jakarta model serves only `/predict/realtime`. No Torch.
- LLM (non-critical path): Groq `qwen/qwen3.8-27b` primary (`DEFAULT_GROQ_MODEL` in `config/llm_config.py`,
  `GROQ_MODEL` overrides), Anthropic Claude optional — explanation and chat only. Chat prompt lives in
  `api/chat_knowledge.txt` (core rules + only the sections the question touches, ~1.5k tokens); the
  free tier allows 8k tokens/min per model, so `/api/chat` falls back to `openai/gpt-oss-20b`, waits out
  a retry-after of ≤ 3 s once, then answers 429 `ai_busy`
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
- Tests: `tests/` (582, `python -m pytest tests -q`); frontend `npm test` in `frontend/` (17: flood roads,
  post levels)
- Frontend: pages Beranda / Evakuasi / Laporan / Tentang; API base in `frontend/src/lib/api.js`;
  onboarding guide `components/OnboardingTour.jsx` (11 steps, reopened from the top-bar "?")

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
- Bundle retrained 2026-10-28 (`scripts/retrain_bundle.py`) with the leak-free
  `kecamatan_historical_flood_freq` (per row, events from earlier years only; inference uses
  years before the snapshot's year), now from BPBD events counted once per RW-date (the workbooks
  list one row per RT; 4,667 events 2020–Mar 2026, was 7,301). Test AUC 0.899 / recall 0.875 /
  precision 0.282 / threshold 0.126. Previous bundles stay in git history (5919525 and earlier).
  Changing `data/bundled/kelurahan_flood_history.json` changes a model input: retrain after rebuilding it.
- The split is still a RANDOM stratified 68/12/20 (train 1990 / val 352 / test 586, 56 test
  positives): the chronological validation slice (May 2023–Jan 2024) has 0 positives, so training
  falls back to random (the report now says so). Test rows are spread over 2020–2024, so the
  metrics above are optimistic. By-year estimate (train 2020–2022, val 2023, test 2024 with 22
  positives): AUC 0.83 [0.75–0.89], PR-AUC 0.12 (no-skill 0.04), ECE 0.17. Run
  `python scripts/evaluate_model.py` for the current figures with 95 % bootstrap CIs.
  Flood labels shrink sharply over time (117/78/54/11/22, 2020–2024).
- No observed row-level flood labels for evaluation: `realtime_feature_history.csv` has no label
  column; `calibration_labeled.csv` labels are synthetic.
- AUC 0.9452 belongs to the legacy Jakarta model (`flood_model_jakarta.pkl`, random 80:20 split).
  Its endpoint `/predict/realtime` was retired 2026-10-24 (410 Gone); the UI uses `/predict/realtime-native`.
- BNPB district mapping gap (kecamatan write-back); InaRISK falls back to bundled static JSON.
- Model experiment 2026-10-27 (by year, test 2024): 609 variants; logistic regression without the proxy
  features ranked floods better (PR-AUC 0.27 vs 0.10) but no variant beat the served model's precision at
  ~86 % recall. The XGBoost candidate without proxies + Platt on the latest year (`scripts/train_candidate.py`,
  `artifacts/reports/candidate_comparison.md`) is worse: AUC 0.796 vs 0.826 after the 2026-10-28 event-count
  fix (was 0.733 vs 0.812). The served bundle stays.
- Label gap (2026-10-28, `scripts/precision_experiments.py`): the training `banjir` label covers only
  276 of the 895 kecamatan-months with a BPBD flood (2020–2024); against BPBD records the by-year
  model's 2024 precision is 0.53, not 0.13. A BPBD-labelled model (by year AUC 0.76, PR-AUC 0.50,
  no-skill 0.26) is a candidate, not served. Daily rainfall alone does not predict flood days
  (`scripts/daily_flood_experiment.py`). BPBD per-kelurahan events exist from 2013 (`events_clean.csv`);
  training stops at 2020–2024 only because the features do.
- Fly stopped/suspended both machines despite `min_machines_running = 1`, halting the 15-minute
  scheduler. `fly.toml` now has `auto_stop_machines = 'off'` (live after the next `fly deploy`); the
  GitHub backup cron still needs repo secrets `REFRESH_URL` + `INTERNAL_SECRET` (and `INTERNAL_SECRET` on Fly).
- Groq free tier: 8k tokens/min per model, so roughly 4–8 chat questions a minute across all users;
  heavier use needs a paid tier.

## Resolved
- 2026-10-24: served model = trained model. The native export kept only fold 0's booster and
  applied all five calibrators to it (per-prediction gap up to 0.32); it now ships one booster per
  calibration fold (`xgboost_model_fold{i}.json`), parity < 1e-6. Calibration method is chosen on
  the validation fold (was the test fold); threshold selection no longer returns 1.0 (recall 0) when
  no threshold reaches the precision floor.
- 2026-10-24: `POST /api/chat` rate-limited per IP (`FLOOD_CHAT_RATE_LIMIT`, Fly client IP from
  `Fly-Client-IP`); `/reports`, `/sos`, `/family/*` off unless `COMMUNITY_API_ENABLED=true`;
  CI in `.github/workflows/ci.yml` (pytest + frontend build).
- 2026-10-27: Groq withdrew `llama-3.3-70b-versatile` (model_not_found → chat always offline); default is
  now `qwen/qwen3.8-27b`. AI answers render bold/lists in the chat bubble.
- 2026-10-27: DSDA water levels arrive in mm and are converted to cm at ingestion (`dsda_mm_to_cm`);
  the L1/L1.8 floors use each post's own DSDA band; `/readyz` checks Supabase; community reports with
  photos (migration 110, bucket `report-photos`); Fly secrets re-imported (were the literal "...").
- 2026-10-27: chat prompt moved server-side (`api/chat_knowledge.txt`, ~5k → ~1.8k tokens), model
  fallback, Groq call off the event loop (one slow answer stalled every request), 429 shown as "busy".
- 2026-10-27: Beranda gauge, Siaga line, wilayah cells and map classify posts by their DSDA band
  (`postRiskLevel` in `frontend/src/lib/dashboardHelpers.js`), like the engine; the ratio is a fallback.
- 2026-10-27: report reactions — likes/dislikes per device, comments, ⋯ menu (share, copy link, Google Maps,
  report); 3 flags hide a report; `/?report=<id>` deep links. Needs `db/migrations/111_report_interactions.sql`
  run in Supabase (until then the endpoints answer 503 and counts show 0).
- 2026-10-27: English page fully English except the 3-agent deep analysis (prompts ask for Indonesian):
  `/predict/realtime-native` returns `risk_interpretation_en` beside `risk_interpretation`. The map legend
  folds on phones. Mentors removed from the About page.
- 2026-10-27: Vercel `VITE_API_BASE_URL` pointed at the old `floodai.fly.dev`; it is now
  `https://floodai-8eclra.fly.dev` (type Config). `html/body` use `overflow-x: clip` so the top bar stays sticky.
- DB CHECK-constraint naming drift (orphan `chk_eval_status` blocked `CONFLICT`/`LOW_TRUST`
  persistence) — fixed by `db/migrations/106_fix_status_constraint_naming_drift.sql`, applied
  to Supabase 2026-06-19.
