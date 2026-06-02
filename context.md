# deFlood.ai — Project Context

> Last updated: 2026-06-03. Update this file whenever architecture, known issues, or deployment state changes.

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI + uvicorn, port 8080 |
| Frontend | React 18 + Vite, port 3000 |
| Database | Supabase / PostgreSQL (psycopg2) |
| ML | XGBoost 3.2.0 + scikit-learn 1.8.0 (AUC 0.945, ECE 0.196) |
| LLM | Groq llama-3.3-70b-versatile (primary) · Anthropic Claude (explain endpoint) |
| CrewAI | crewai 1.14.0 + litellm 1.87.0 |
| Deploy | Railway (backend) · Vercel (frontend) |

---

## Run

```bash
# Backend
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload

# Frontend — dev mode, gunakan Vite proxy (tidak perlu set VITE_API_BASE_URL)
cd frontend && npm run dev

# Refresh snapshot manual (opsional — scheduler otomatis tiap 15 menit)
cd poskobanjir && python main.py
```

---

## Key paths

| Path | Fungsi |
|---|---|
| `api/main.py` | FastAPI app, CORS middleware, scheduler, semua endpoints |
| `api/routes/agentic_llm.py` | `POST /predict/agentic/explain` |
| `api/routes/chat.py` | `POST /api/chat` (Groq chatbot, tanpa auth) |
| `api/routes/crew_analysis.py` | `POST /predict/crew-analysis` (CrewAI) |
| `agents/crew/flood_crew.py` | CrewAI 3-agent crew implementation |
| `agents/llm_orchestrator.py` | Groq/Claude single-pass explanation |
| `pipeline/flood_pipeline.py` | Orchestrator 5-stage pipeline |
| `services/decision_engine.py` | Canonical decision authority (L0–L4 hierarchy) |
| `services/snapshot_refresh.py` | APScheduler: jalankan subprocess tiap 15 menit |
| `realtime_native/feature_builder.py` | Build 16 fitur dari snapshot |
| `realtime_native/inference.py` | `GET /predict/realtime-native` |
| `poskobanjir/main.py` | Pipeline scraper: TMA + OpenWeather + BMKG → snapshot JSON |
| `poskobanjir/data/clean/realtime_snapshot.json` | Snapshot aktif (diupdate tiap 15 menit) |
| `frontend/src/pages/Home.jsx` | Command center (metrics, peta, zona risiko) |
| `frontend/src/lib/floodAgent.js` | Chat backend call + offline KB fallback |
| `frontend/src/lib/humanize.js` | `humanizeRainfall()`, `humanizeRiskLevel()` |
| `frontend/src/hooks/useFloodRisk.js` | Poll `GET /predict/realtime-native` tiap 15 menit |
| `frontend/src/hooks/useChat.js` | Chat state + `aiOnline` tracking |
| `frontend/src/components/ChatBot.jsx` | Chat FAB + online/offline indicator |
| `frontend/vite.config.js` | Dev proxy `/predict/*` dan `/api/*` → port 8080 |

---

## Endpoints

| Endpoint | Auth | Deskripsi |
|---|---|---|
| `GET /predict/realtime-native` | — | XGBoost inference dari snapshot file |
| `POST /predict/agentic` | X-Api-Key | Full 5-stage agentic pipeline |
| `POST /predict/agentic/explain` | X-Api-Key | Pipeline + LLM explanation (Bahasa Indonesia) |
| `POST /predict/crew-analysis` | X-Api-Key | Pipeline + CrewAI 3-agent analysis |
| `POST /api/chat` | — | Groq chatbot bilingual (ID/EN) |
| `GET /healthz` | — | Liveness check |
| `GET /readyz` | — | Readiness check (DB + thresholds) |
| `GET /metrics` | — | Prometheus metrics |
| `POST /internal/refresh-snapshot` | X-Internal-Secret | Manual snapshot refresh |

**API key default:** `FLOOD_API_KEYS=demo123` di `.env`

---

## Prediction pipeline (5 stage)

```
POST /predict/agentic
  └── [1] PerceptionAgent   — validasi snapshot, plausibility score
  └── [2] ReasoningAgent    — XGBoost inference, OOD detection, baseline
  └── [3] EvaluationAgent   — risk reconciliation, trust scoring
  └── [4] ActionAgent       — format final JSON output
  └── [5] RoutingAgent      — rute evakuasi (OSRM)
```

### Decision hierarchy (decision_engine.py)
- **L0 PHYSICAL** — input tidak valid → UNKNOWN
- **L1 SIAGA** — water_level_ratio ≥ 0.90 → DANGER
- **L1.5 MULTI** — ≥2 dari {rainfall ≥ 60mm, water_level ≥ 0.85, bmkg ≥ 0.80} → DANGER
- **L2 INTEGRITY** — failure severe → eskalasi satu level
- **L3 ML** — probabilitas vs adaptive threshold
- **L1.8 HYDRO_FLOOR** — post-ML floor (ratio ≥ 0.75 → WARNING)
- **L4 TREND** — tren naik sustained → WARNING→DANGER

---

## CrewAI (agents/crew/flood_crew.py)

3 agen berjalan **sekuensial** setelah ML pipeline selesai:

```
AhliCuaca (Meteorolog BMKG)
    input: rainfall_mm, humidity, bmkg_weighted_score, BMKG alerts
    output: analisis cuaca 2–3 kalimat
         ↓
AhliHidrologi (Dinas SDA DKI)
    input: water_level_ratio, delta, stasiun PDA, hydro_index
    output: analisis hidrologi 2–3 kalimat
         ↓
KoordinatorRisiko (Pusdalops BPBD)
    input: ML prediction + kedua analisis di atas
    output: JSON lengkap (status, penjelasan, tindakan, dll.)
```

- Model: `groq/llama-3.3-70b-versatile` via litellm
- Timeout total: 45 s (env var `CREW_TIMEOUT_S`)
- Per-request HTTP timeout: 20 s
- Fallback deterministik jika crew gagal
- **Output dijamin 8 kunci:** `status_banjir`, `penjelasan`, `tindakan`, `populasi_terdampak`, `tingkat_kepercayaan`, `pesan_petugas`, `analisis_cuaca`, `analisis_hidrologi`

---

## Frontend

### Halaman
| Route | Komponen | Fungsi |
|---|---|---|
| `/` | `Home.jsx` | Command center — metrics, peta, zona risiko |
| `/alert` | `Alert.jsx` | Status alert aktif |
| `/evacuation` | `EvacuationMap.jsx` | Rute evakuasi ke shelter |
| `/chat` | `Chat.jsx` | Dedicated chat page |
| `/about` | `About.jsx` | Info project |

### Rainfall display
`humanizeRainfall()` dari `humanize.js` mengkonversi mm/jam ke label:
- `0` → "Tidak ada hujan" / "No rain"
- `< 5` → "Gerimis" / "Drizzle"
- `5–20` → "Hujan sedang" / "Moderate rain"
- `20–50` → "Hujan lebat" / "Heavy rain"
- `50–100` → "Hujan sangat lebat" / "Very heavy rain"
- `≥ 100` → "Hujan ekstrem" / "Extreme rain"

### Chat behaviour
- **`● AI Online`**: backend Groq berhasil menjawab → `isAI: true`
- **`○ Offline (KB)`**: backend tidak terjangkau → keyword fallback → `isAI: false`
- Pesan dari offline KB diberi label kecil `"offline KB"` di bubble

### Dev proxy
`vite.config.js` memforward `/predict/*` dan `/api/*` → `localhost:8080`.
Browser tidak pernah buat cross-origin request saat development.
- **Dev:** biarkan `VITE_API_BASE_URL=` kosong di `.env.local`
- **Production (Vercel):** set `VITE_API_BASE_URL=https://backend.railway.app`

---

## Data flow (snapshot & rainfall)

```
poskobanjir/main.py (subprocess, tiap 15 menit via APScheduler)
  ├── fetch_openweather()     → weather.rain.1h  (field hadir HANYA saat hujan)
  ├── fetch_poskobanjir_xml() → 38 stasiun TMA   (TMA scraper broken, fallback ada)
  └── fetch_bmkg_feed()       → alert BMKG aktif
            ↓
  poskobanjir/data/clean/realtime_snapshot.json
            ↓
  GET /predict/realtime-native
    → feature_builder: rain_data.get("1h") → rainfall_mm
    → XGBoost → risk_level, probability
            ↓
  frontend useFloodRisk()
    → rainfall = json.features?.rainfall_mm ?? 0
    → tampil sebagai humanizeRainfall(rainfall)
```

---

## Known issues

| Issue | Status | Dampak |
|---|---|---|
| TMA scraper broken | Aktif | Data tinggi air bisa kosong; fallback ke Supabase snapshot |
| Calibration deactivated | Aktif | ECE 0.3784 (target < 0.10); confidence score kurang akurat |
| BNPB district mapping gap | Aktif | Beberapa kecamatan tidak ter-map ke kabkot |

---

## Environment variables

```bash
# .env (project root — wajib)
FLOOD_API_KEYS=demo123              # comma-separated; gunakan random string di production
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile
LLM_PROVIDER=groq                   # groq | anthropic
OPENWEATHER_API_KEY=...
SUPABASE_URL=...
SUPABASE_KEY=...
DATABASE_URL=...

# .env (opsional)
ANTHROPIC_API_KEY=sk-ant-...        # untuk /predict/agentic/explain via Claude
CREW_TIMEOUT_S=45                   # CrewAI wall-clock timeout (default 45)

# frontend/.env.local (jangan dicommit)
VITE_API_BASE_URL=                  # kosong = Vite proxy (dev)
                                    # https://backend.railway.app (production)
```

---

## Recent commits

```
3e88f40 feat: integrate CrewAI + fix rainfall display + fix chat online/offline
98c4b1d docs: rewrite context.md — clean full project state 2026-06-02
2de65fb fix: resolve 10 issues — map bias, chatbot KB, snapshot fallback, translations
9b5c5cb fix: chatbot offline fallback + navbar bigger + mobile fix + About LinkedIn
c52a1ff fix: resolve 6 issues — calibration, temporal features, scraper degradation, zone biases
```
