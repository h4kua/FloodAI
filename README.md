# AI Flood Response Agent System

Production-grade, multi-agent flood prediction and decision system for DKI
Jakarta. Fuses real-time hydrometeorological signals with administrative
vulnerability data and serves explainable risk decisions over a FastAPI surface.

## Overview

- Dual ML models: `legacy_geospatial` (historical, feature-rich) and
  `realtime_native` (operationally aligned, deployment-ready).
- Four-agent pipeline — Perception, Reasoning, Evaluation, Action — orchestrated
  by `FloodDecisionPipeline` with per-stage timeouts and idempotency.
- BNPB InaRISK vulnerability gate with kecamatan-level resolution and static
  fallback when the upstream API is unreachable.
- DEMNAS elevation context (flood-zone classification, flow direction) when DEM
  tiles are available; falls open when missing.
- Postgres persistence for snapshots, agent stages, decisions, trust
  breakdowns, and replay scenarios.

## Architecture

```
[Snapshot In] -> SnapshotIn (Pydantic, location-normalised)
              -> FloodDecisionPipeline
                 |- PerceptionAgent  (BNPB + DEM + signals)
                 |- ReasoningAgent   (model inference + adaptive threshold)
                 |- EvaluationAgent  (plausibility + failure modes)
                 |- ActionAgent      (decision + routing)
              -> Postgres (pipeline_runs, perception, reasoning,
                 evaluation, decisions, trust_breakdowns)
              -> JSON response (risk_level, probability, bnpb_status,
                 elevation, decision_trace, safe_route)
```

## Quick Start

```bash
python -m venv flood_env
flood_env\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env              # then fill in DB + API keys
uvicorn api.main:app --reload
```

Open `http://localhost:8000/docs` for interactive Swagger UI.

## API Usage

| Method | Path                       | Auth | Purpose                          |
|--------|----------------------------|------|----------------------------------|
| GET    | `/healthz`                 | no   | Liveness                         |
| GET    | `/readyz`                  | no   | DB + thresholds readiness        |
| GET    | `/metrics`                 | yes  | Prometheus metrics               |
| GET    | `/predict/realtime`        | yes  | Legacy model on latest snapshot  |
| GET    | `/predict/realtime-native` | no   | Realtime-native model            |
| POST   | `/predict/agentic`         | yes  | Full agentic pipeline on payload |
| GET    | `/demo`                    | yes  | HTML dashboard                   |

### Working demo

```bash
curl -X POST http://localhost:8000/predict/agentic \
  -H "x-api-key: dev-local-key" \
  -H "Content-Type: application/json" \
  -d '{
    "fetched_at_utc": "2026-05-18T11:30:00Z",
    "location": "Jakarta Utara",
    "openweather": {"main": {"temp": 27.9, "humidity": 91}, "rain": {"1h": 20}, "coord": {"lat": -6.2088, "lon": 106.8456}},
    "poskobanjir": [{"wilayah": "Jakarta Utara", "tinggi_air": 120, "status": "Siaga 3"}],
    "bmkg_alerts": [{"headline": "Hujan Lebat Jakarta", "severity": "Moderate", "certainty": "Observed", "urgency": "Immediate"}]
  }'
```

`location` accepts a canonical kota string (e.g. `"Jakarta Utara"`), a
kecamatan name (`"Menteng"` → Jakarta Pusat), or a dict
(`{"district": "Menteng"}`) — the schema-level validator normalises all forms
and falls back to `Jakarta Utara` on ambiguous input. `Idempotency-Key` is
honoured for one hour.

## Key Features

- Schema-level location normaliser — never raises, always yields a valid kota.
- BNPB vulnerability gate with status codes `ACTIVE` / `STATIC_FALLBACK` /
  `DEFAULT` / `NOT_APPLICABLE`.
- Adaptive risk threshold with shadow evaluation and override trace.
- Out-of-distribution detection on `realtime_native` features.
- Per-stage circuit breakers, request budget, and graceful degradation.
- Idempotent POST with response-hash drift detection.
- Audit-grade observability: request-id middleware, structured logs,
  Prometheus metrics, trust breakdowns.

## Data Sources

- **Posko Banjir DKI** — water heights and siaga status (`poskobanjir/`).
- **BMKG CAP / Nowcast** — severity, certainty, urgency alerts.
- **OpenWeather** — temperature, humidity, rainfall, coordinates.
- **BNPB InaRISK** — kelurahan vulnerability index (live + static fallback in
  `data/bundled/bnpb_jakarta_fallback.json`).
- **DEMNAS** — 8 m DEM tiles for elevation context. Place tiles in `data/elevation/`:
  `DEMNAS_1209-42_v1.0.tif`, `DEMNAS_1209-43_v1.0.tif`,
  `DEMNAS_1209-44_v1.0.tif`. Missing tiles fail open — elevation fields
  return `None` / `"unknown"` and the API keeps serving.

## Test Suite

```bash
pytest tests/ --tb=short
```

Current baseline: **393 passed / 4 known failures** (failure-simulation x3 +
migration-runner x1, all unrelated to the serving path). Coverage spans unit,
integration, route, persistence, and failure-injection layers.

## Environment Variables

See `.env.example` for the full template. The critical ones:

| Variable                   | Purpose                                  |
|----------------------------|------------------------------------------|
| `FLOOD_API_KEYS`           | Comma-separated keys for `x-api-key`     |
| `FLOOD_API_RATE_LIMIT`     | Per-key requests / minute                |
| `FLOOD_REQUEST_BUDGET_S`   | Per-request timeout budget               |
| `ALLOWED_HOSTS`            | Trusted-host allowlist                   |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | Postgres |
| `OPENWEATHER_API_KEY`      | Snapshot ingestion                       |
| `ANTHROPIC_API_KEY`        | LLM-assisted reasoning narratives        |
| `GOOGLE_MAPS_API_KEY`      | Safe-route generation                    |
| `BNPB_DEFAULT_VINTAGE_DAYS`| Fallback vintage when InaRISK is silent  |
| `FLOOD_ALLOW_RUNTIME_SCRAPE` | Set `1` to enable on-demand scraping   |
| `MODEL_PATH` / `SCALER_PATH` / `THRESHOLD_PATH` | Model artifacts paths |
