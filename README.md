# FloodAI — Agentic Flood Decision System

Production-grade, multi-agent flood prediction and decision system for DKI Jakarta.
Fuses real-time hydrometeorological signals with administrative vulnerability data
and serves explainable risk decisions over a FastAPI surface.

---

## Overview

- **Dual ML models** — `legacy_geospatial` (historical, feature-rich) dan `realtime_native` (operationally aligned, deployment-ready)
- **Four-agent pipeline** — Perception → Reasoning → Evaluation → Action — diorkestrasikan oleh `FloodDecisionPipeline` dengan per-stage timeouts dan idempotency
- **LLM-assisted reasoning** via [Groq](https://groq.com) (`llama-3.3-70b-versatile`) — cepat, free-tier friendly
- **BNPB InaRISK** vulnerability gate dengan resolusi kecamatan + static fallback
- **DEMNAS elevation context** (flood-zone classification, flow direction) ketika DEM tiles tersedia
- **Postgres / Supabase** persistence untuk snapshots, agent stages, decisions, trust breakdowns, dan replay

---

## Architecture

```
[POST /predict/agentic]
        │
        ▼
  SnapshotIn (Pydantic, location-normalised)
        │
        ▼
  FloodDecisionPipeline
  ├── PerceptionAgent   → BNPB + DEM + sensor signals
  ├── ReasoningAgent    → ML inference + adaptive threshold + Groq LLM
  ├── EvaluationAgent   → plausibility check + failure mode detection
  └── ActionAgent       → risk decision + safe-route generation
        │
        ▼
  Supabase (PostgreSQL)
  └── pipeline_runs, perception, reasoning, evaluation, decisions, trust_breakdowns
        │
        ▼
  JSON Response
  └── risk_level, probability, bnpb_status, elevation, decision_trace, safe_route
```

---

## Project Structure

```
FloodAI/
├── api/                → FastAPI app, routes, middleware
├── agents/             → AI agents (Groq LLM — Perception, Reasoning, Evaluation, Action)
├── core/               → Core business logic
├── domain/             → Domain models & entities
├── contracts/          → API schemas & contracts (Pydantic)
├── services/           → Integrasi layanan eksternal (BMKG, BNPB, OpenWeather)
├── pipeline/           → Data processing pipeline
├── db/                 → Database layer (migrations, repositories)
├── config/             → Configuration loaders
├── monitoring/         → Observability & Prometheus metrics
├── evaluation/         → ML model evaluation
├── realtime_native/    → Realtime native model module
├── utils/              → Shared utilities
├── models/             → ML model files (.pkl, .json, thresholds)
├── data/               → Datasets (raw, processed, bundled, elevation)
├── notebooks/          → Jupyter notebooks (exploratory & production)
├── tests/              → Test suite (unit, integration, fixtures)
├── scripts/            → Utility & migration scripts
├── docs/               → Guides & documentation
├── frontend/           → Frontend dashboard
├── artifacts/          → Reports, visualizations, configurations
├── poskobanjir/        → Flood monitoring post data service
├── Dockerfile          → Container build untuk Fly.io
├── fly.toml            → Konfigurasi deployment Fly.io
├── requirements.txt    → Python dependencies
├── pyproject.toml      → Project configuration
└── .env.example        → Environment variable template
```

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/h4kua/FloodAI.git
cd FloodAI

# 2. Setup virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
copy .env.example .env        # Windows
# cp .env.example .env        # Linux/Mac
# Edit .env dan isi API keys + DB credentials

# 5. Run
uvicorn api.main:app --reload --port 8000
```

Buka `http://localhost:8000/docs` untuk Swagger UI interaktif.

---

## API Endpoints

| Method | Path                         | Auth | Purpose                           |
|--------|------------------------------|------|-----------------------------------|
| GET    | `/healthz`                   | ✗    | Liveness check                    |
| GET    | `/readyz`                    | ✗    | DB + thresholds readiness         |
| GET    | `/metrics`                   | ✓    | Prometheus metrics                |
| GET    | `/predict/realtime`          | ✓    | Legacy model on latest snapshot   |
| GET    | `/predict/realtime-native`   | ✗    | Realtime-native model             |
| POST   | `/predict/agentic`           | ✓    | Full agentic pipeline on payload  |
| GET    | `/demo`                      | ✓    | HTML dashboard                    |

### Contoh Request

```bash
curl -X POST http://localhost:8000/predict/agentic \
  -H "x-api-key: demo123" \
  -H "Content-Type: application/json" \
  -d '{
    "fetched_at_utc": "2026-05-18T11:30:00Z",
    "location": "Jakarta Utara",
    "openweather": {
      "main": {"temp": 27.9, "humidity": 91},
      "rain": {"1h": 20},
      "coord": {"lat": -6.2088, "lon": 106.8456}
    },
    "poskobanjir": [
      {"wilayah": "Jakarta Utara", "tinggi_air": 120, "status": "Siaga 3"}
    ],
    "bmkg_alerts": [
      {
        "headline": "Hujan Lebat Jakarta",
        "severity": "Moderate",
        "certainty": "Observed",
        "urgency": "Immediate"
      }
    ]
  }'
```

`location` menerima nama kota (`"Jakarta Utara"`), kecamatan (`"Menteng"` → Jakarta Pusat),
atau dict (`{"district": "Menteng"}`). Schema validator menormalkan semua bentuk input.

---

## Environment Variables

Salin `.env.example` ke `.env` lalu isi nilai-nilainya:

| Variable                                  | Keterangan                                        |
|-------------------------------------------|---------------------------------------------------|
| `FLOOD_API_KEYS`                          | API keys untuk header `x-api-key` (koma-separated)|
| `FLOOD_API_RATE_LIMIT`                    | Max request per menit per key                     |
| `FLOOD_REQUEST_BUDGET_S`                  | Budget timeout per request (detik)                |
| `ALLOWED_HOSTS`                           | Trusted host allowlist                            |
| `DATABASE_URL`                            | PostgreSQL connection string (Supabase)           |
| `DB_HOST` / `DB_PORT` / `DB_NAME`         | DB credentials                                    |
| `DB_USER` / `DB_PASSWORD`                 | DB credentials                                    |
| `SUPABASE_URL`                            | Supabase project URL                              |
| `SUPABASE_KEY`                            | Supabase anon key                                 |
| `LLM_PROVIDER`                            | `groq` (default) atau `anthropic`                 |
| `GROQ_API_KEY`                            | API key dari [console.groq.com](https://console.groq.com) |
| `GROQ_MODEL`                              | Model Groq (default: `llama-3.3-70b-versatile`)   |
| `OPENWEATHER_API_KEY`                     | Snapshot ingestion cuaca                          |
| `GOOGLE_MAPS_API_KEY`                     | Generasi safe-route                               |
| `BNPB_DEFAULT_VINTAGE_DAYS`               | Fallback vintage saat InaRISK tidak tersedia      |
| `MODEL_PATH` / `SCALER_PATH`              | Path ke file model ML                             |
| `THRESHOLD_PATH`                          | Path ke file optimal threshold                    |

---

## Data Sources

| Sumber | Keterangan |
|--------|------------|
| **Posko Banjir DKI** | Tinggi air & status siaga (`poskobanjir/`) |
| **BMKG CAP / Nowcast** | Alert severity, certainty, urgency |
| **OpenWeather** | Suhu, kelembaban, curah hujan, koordinat |
| **BNPB InaRISK** | Indeks kerentanan kelurahan (live + static fallback di `data/bundled/`) |
| **DEMNAS** | DEM 8 m untuk konteks elevasi — letakkan tile di `data/elevation/` |

---

## Key Features

- **Location normaliser** — menerima kota, kecamatan, atau dict; tidak pernah raise error
- **BNPB vulnerability gate** — status `ACTIVE` / `STATIC_FALLBACK` / `DEFAULT` / `NOT_APPLICABLE`
- **Adaptive risk threshold** — shadow evaluation + override trace
- **Out-of-distribution detection** pada fitur `realtime_native`
- **Per-stage circuit breakers** — request budget + graceful degradation
- **Idempotent POST** — response-hash drift detection (berlaku 1 jam)
- **Audit-grade observability** — request-id middleware, structured logs, Prometheus metrics, trust breakdowns

---

## Tests

```bash
pytest tests/ --tb=short
```

Baseline: **393 passed / 4 known failures** (failure-simulation ×3 + migration-runner ×1, semua di luar serving path).
Coverage: unit, integration, route, persistence, dan failure-injection.

---

## Deployment (Fly.io)

Project ini dikonfigurasi untuk deploy ke [Fly.io](https://fly.io) menggunakan Docker.

```bash
# Install flyctl terlebih dahulu:
# https://fly.io/docs/hands-on/install-flyctl/

flyctl auth login
flyctl deploy
```

Konfigurasi ada di `fly.toml` (region: Singapore, port: 8080, memory: 512MB).
Set environment variables via Fly.io dashboard atau CLI:

```bash
flyctl secrets set GROQ_API_KEY=your_key FLOOD_API_KEYS=your_key DATABASE_URL=your_url
```

---

## License

MIT
