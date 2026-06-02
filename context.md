# deFlood.ai — Project Context

> Last updated: 2026-06-02. Update this file whenever architecture, known issues, or deployment state changes.

---

## Project Overview

**deFlood.ai** adalah sistem prediksi dan kecerdasan banjir berbasis AI untuk Jakarta. Menggabungkan data sensor realtime, model machine learning XGBoost, dan AI generatif (Groq Llama 3.3-70B) untuk membantu operator BPBD dan warga Jakarta memantau serta merespons risiko banjir.

- **Kompetisi**: AI for Environmental & Social Impact
- **Author**: JuanVier (@juanvier_ / LinkedIn: juanjaviersz)
- **Repo**: https://github.com/h4kua/FloodAI

---

## Stack & Deployment

| Layer | Teknologi | Deploy |
|---|---|---|
| Backend API | FastAPI + Uvicorn, port 8080 | Fly.dev |
| Frontend | React 18 + Vite 5 | Vercel |
| Database | Supabase / PostgreSQL | Supabase (ap-south-1) |
| ML Runtime | XGBoost 3.2.0 + scikit-learn 1.8.0 | bundled di Fly.dev |
| AI Chat | Groq API (llama-3.3-70b-versatile) | via Fly.dev env |
| Map | React-Leaflet + OpenStreetMap | client-side |
| Geocoding | Nominatim / OSM + OSRM routing | public API |

### Run lokal

```bash
# Backend (dari project root)
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload

# Frontend
cd frontend && npm run dev
```

### Env vars wajib

- **Backend** (root `.env`): `GROQ_API_KEY`, `OPENWEATHER_API_KEY`, `DATABASE_URL`, `DB_HOST/PORT/NAME/USER/PASSWORD`, `FLOOD_API_KEYS`
- **Frontend** (`frontend/.env.local` untuk lokal, Vercel dashboard untuk production):
  - Lokal: `VITE_API_BASE_URL=http://localhost:8080`
  - Production: `VITE_API_BASE_URL=https://floodai.fly.dev`

> **Penting**: `VITE_API_BASE_URL` di root `.env` **tidak dibaca Vite** — hanya untuk referensi. Vite baca dari `frontend/.env*`.

---

## Arsitektur Backend

```
api/
  main.py              — FastAPI app, APScheduler (refresh snapshot tiap 15 menit)
  routes/
    chat.py            — POST /api/chat (Groq LLM) — no API key required
    agentic_llm.py     — POST /predict/agentic (5-stage pipeline) — requires X-Api-Key
  observability.py     — logging, metrics, middleware
  security.py          — API key auth (FLOOD_API_KEYS)

pipeline/
  flood_pipeline.py    — 5-stage agentic decision pipeline

agents/
  perception_agent.py  — stage 1: baca snapshot, ekstrak features
  reasoning_agent.py   — stage 2: reasoning + threshold check
  evaluation_agent.py  — stage 3: evaluasi risiko
  action_agent.py      — stage 4: rekomendasi aksi
  routing_agent.py     — stage 5: evakuasi routing

realtime_native/
  bundle.py            — load model bundle (hash validation, version check)
  inference.py         — GET /predict/realtime-native (endpoint utama frontend, no auth)
  feature_builder.py   — build 16 features dari snapshot (DB → CSV fallback → Supabase)
  training.py          — retrain model

services/
  decision_engine.py   — threshold logic, calibration cache reader
  snapshot_refresh.py  — build fresh snapshot (subprocess poskobanjir → Supabase fallback)
  shelter_locator.py   — haversine nearest shelter
  bnpb_jakarta_mapper.py — kecamatan → kabkot mapping
  bmkg_filter.py       — filter BMKG alerts hanya untuk Jakarta
  ... (30+ service files)

db/
  psycopg2_connection.py — ThreadedConnectionPool ke Supabase PostgreSQL
  snapshot_repository.py — save/load realtime snapshot ke Supabase
  supabase_client.py     — lazy HTTP client (fallback jika psycopg2 gagal)

poskobanjir/
  main.py              — scraper pipeline (graceful degradation: lanjut jika TMA offline)
  services/fetcher.py  — fetch XML dari poskobanjir.dsdadki.web.id + OpenWeather + BMKG
  processing/cleaner.py

evaluation/
  calibration.py       — compute ECE, Brier score
  metrics.py, scenario_runner.py

scripts/
  process_bpbd.py               — proses CSV BPBD → flood calendar + zone frequency
  run_calibration_from_bpbd.py  — kalibrasi ulang model dari data BPBD
```

### Endpoint summary

| Endpoint | Auth | Deskripsi |
|---|---|---|
| `GET /predict/realtime-native` | none | Prediksi utama frontend (XGBoost) |
| `POST /api/chat` | none | Chatbot Groq LLM |
| `POST /predict/agentic` | `X-Api-Key` | 5-stage agentic pipeline |
| `GET /healthz` / `/health` | none | Liveness check |
| `GET /readyz` | none | Readiness check (DB + model) |
| `POST /internal/refresh-snapshot` | `X-Internal-Secret` | Manual snapshot refresh |

---

## Arsitektur Frontend

```
frontend/src/
  App.jsx              — shell: topbar (68px), nav, theme/lang toggle
  styles.css           — semua CSS (design tokens, responsive, overflow-x hidden)
  pages/
    Home.jsx           — Command Center: 4 metrics, peta, zone table, chatbot
    Alert.jsx          — Evacuation: address input, OSRM route, shelter locator
    About.jsx          — tech info, disclaimer, LinkedIn link
  components/
    ChatBot.jsx        — floating chatbot FAB (6 quick replies, offline KB fallback)
    FloodMap.jsx       — Leaflet peta DKI Jakarta + risk overlay (5 kotamadya)
    EvacuationMap.jsx  — peta rute evakuasi (OSRM)
    EmergencyContacts.jsx — kontak darurat BPBD, Basarnas, dll
  hooks/
    useFloodRisk.js    — polling /predict/realtime-native tiap 15 menit
    useChat.js         — state management chat history (try/catch/finally)
  lib/
    floodAgent.js      — kirim ke /api/chat + OFFLINE KB fallback (10 topik, ID+EN)
    translations.js    — semua string bilingual ID/EN
    appContext.jsx      — React context: lang + theme
```

### Fitur Frontend

- Dark/light theme, persisted localStorage
- Bilingual ID/EN, auto-detect dari bahasa pesan chatbot
- 4 metric cards: zona siaga, warga terdampak, skor risiko, curah hujan
- Zone table 5 zona dengan bias data-driven BPBD
- TMA label `○ est.` (estimasi), Rainfall label `● real` (OpenWeather)
- Chatbot offline KB 10 topik: evakuasi, status, tanda banjir, shelter, kontak, dokumen, cuaca, pasca banjir, prediksi, pompa
- 6 quick replies di chatbot
- FloodMap: 5 kotamadya dengan bias konsisten BPBD
- Mobile responsive: `overflow-x: hidden`, topbar collapse di ≤640px

---

## ML Model

### Model: `realtime_native`

| Param | Value |
|---|---|
| Type | XGBoost Classifier + CalibratedClassifierCV (isotonic) |
| Bundle version | 2.0.0 (schema v2) |
| Created | 2026-05-23 |
| AUC-ROC | 0.9452 |
| Accuracy | 0.9437 |
| F1 | 0.9439 |
| **ECE (calibration)** | **0.1962** (n=1,391) — dikalibrasi dari BPBD 2024–2026 |
| Brier score | 0.103 |
| Training records | 2,928 Jakarta 2013–2026 |

### 16 Features input

`rainfall_mm`, `rainfall_3h_proxy_mm`, `rainfall_lag_1`, `rainfall_lag_2`, `rainfall_roll3_mean`, `humidity_pct`, `temperature_c`, `bmkg_severity_score`, `bmkg_certainty_score`, `bmkg_urgency_score`, `bmkg_weighted_score`, `water_level_ratio`, `water_level_lag_1`, `water_level_delta`, `hydro_meteorological_index`, `monsoon_season`

### Risk thresholds (realtime_native)

| Level | Probabilitas |
|---|---|
| SAFE | < 0.142 |
| WARNING | 0.142 – 0.242 |
| DANGER | ≥ 0.242 |

### Bundle path

`models/realtime_native_bundle/manifest.json` — hash SHA256 validation + sklearn/xgboost version check (major.minor harus match persis).

### Runtime versions (wajib match)

Python 3.12.10 · sklearn 1.8.0 · xgboost 3.2.0 · joblib 1.4.2 · numpy 1.26.4

---

## Data Sources

### Realtime

| Sumber | Data | Status |
|---|---|---|
| `poskobanjir.dsdadki.web.id/xmldata.xml` | TMA sungai Jakarta | **OFFLINE** — server DSDADKI mati |
| OpenWeather API | curah hujan, suhu, kelembapan | OK |
| BMKG nowcast feed | alert cuaca ekstrem | OK (filter Jakarta saja) |

> Ketika TMA offline: pipeline graceful degrade, OpenWeather + BMKG tetap jalan. TMA di frontend ditampilkan sebagai `○ est.`.
> Ketika SEMUA sumber offline: `snapshot_refresh.py` load snapshot terakhir dari Supabase cache.

### Historical / Static

| File | Isi |
|---|---|
| `data/raw/bpbd_banjir_2024.csv` | BPBD kejadian banjir Jakarta 2024 |
| `data/raw/bpbd_banjir_2025_2026.csv` | BPBD 2025 Q1–Q3 + 2026 Q1 |
| `data/raw/data_banjir_combine_final.csv` | Dataset training 2013–2026 |
| `data/processed/bpbd_flood_calendar.csv` | Quarterly flood flag dari BPBD |
| `data/processed/zone_flood_frequency.csv` | Event count per zona → sumber zone biases |
| `data/processed/calibration_labeled.csv` | 1,391 labeled rows untuk kalibrasi ECE |
| `data/processed/realtime_feature_history.csv` | 1,406 rows riwayat temporal features (CSV fallback) |
| `artifacts/configurations/calibration_cache.json` | ECE 0.1962, Brier 0.103, n=1,391 |
| `models/realtime_native_bundle/` | Model bundle: pkl, json, manifest |

---

## Zone Biases (data-driven BPBD)

### Zone table — Home.jsx (kecamatan-level)

| Zona | Wilayah | Bias | BPBD Events |
|---|---|---|---|
| Kebayoran | Jakarta Selatan | **+20** | 239 — paling sering banjir |
| Penjaringan | Jakarta Utara | +6 | 158 |
| Jatinegara | Jakarta Timur | +6 | 157 — OOD flag |
| Kalideres | Jakarta Barat | +4 | 144 |
| Cengkareng | Jakarta Barat | -1 | 114 |

### FloodMap — FloodMap.jsx (kotamadya-level)

| Kotamadya | Bias | Catatan |
|---|---|---|
| Jakarta Selatan | +18 | Tertinggi per BPBD |
| Jakarta Utara | +6 | |
| Jakarta Timur | +5 | |
| Jakarta Barat | +3 | Rata-rata Kalideres + Cengkareng |
| Jakarta Pusat | -4 | Terendah |

> Bias lama FloodMap salah besar: Jakarta Selatan di-set -18 (diasumsikan paling aman), padahal event count BPBD tertinggi. Sudah dikoreksi.

---

## Known Issues

### MASIH OPEN ⚠️

| Issue | Keterangan |
|---|---|
| TMA sensor DSDADKI offline | Server fisik mati, bukan kode. TMA masih estimasi sampai DSDADKI aktif kembali |
| Zone data masih estimasi | 5 zona derived dari 1 ML score + bias, bukan sensor per-kecamatan. Fix butuh sensor DSDADKI |
| BNPB kecamatan write-back | Mapping kota → kecamatan reverse belum fully populated di pipeline output (hanya mempengaruhi `/predict/agentic`, tidak di frontend) |
| DB lokal timeout | Supabase hanya tersambung dari Fly.dev, bukan lokal. CSV + Supabase fallback aktif |

### SELESAI ✅ (semua batch)

| Issue | Fix |
|---|---|
| TMA scraper abort pipeline | Graceful degradation — tiap sumber dibungkus try/except |
| ECE 0.38 n=7 | Dikalibrasi ulang → ECE 0.20 n=1,391 dari data BPBD |
| Calibration cache path bug | `"..", ".."` → `".."` di `decision_engine.py` |
| Temporal features selalu 0 | `FEATURE_HISTORY_DB_ENABLED=false` + CSV fallback di `feature_builder.py` |
| Zone biases salah (Kebayoran) | Data-driven dari BPBD (Kebayoran -22 → +20) |
| FloodMap bias salah (Jakarta Selatan -18) | Di-fix ke +18 sesuai BPBD data |
| Chatbot offline KB terbatas | Expanded ke 10 topik ID+EN di `floodAgent.js` |
| ChatBot quick replies hanya 3 | Diperluas ke 6, translation keys chat.q1–q6 |
| `evac.searching` translation key hilang | Ditambahkan di `translations.js` (ID+EN) |
| `useChat.js` loading macet jika error | try/catch/finally ditambahkan |
| Chatbot "AI tidak tersedia" | Offline KB fallback aktif sebelum generic message |
| Risk score tampil 0 | Probabilitas < 1% tampil sebagai 1 |
| Navbar terlalu kecil | Topbar 58px → 68px |
| Mobile horizontal scroll | `overflow-x: hidden` pada html/body |
| About page tanpa LinkedIn | Tombol LinkedIn (juanjaviersz) ditambahkan |
| `frontend/.env.example` salah var | `VITE_API_URL` → `VITE_API_BASE_URL` |
| Frontend tidak bisa konek backend lokal | `frontend/.env.local` dibuat (`http://localhost:8080`) |
| Snapshot kosong saat semua sumber offline | `snapshot_refresh.py` fallback ke Supabase cache |
| Snapshot file missing (fresh clone) | `feature_builder.py` fallback ke Supabase sebelum FileNotFoundError |
| catalog.json path stale (`app/` prefix) | 5 path dikoreksi: `services/`, `api/`, `realtime_native/` |
| `psycopg2_connection.py` indentasi | `get_psycopg2_connection()` diformat ulang |
| `apscheduler` missing lokal | `pip install apscheduler` |

---

## Key Paths

```
api/main.py                                     — FastAPI entry point
services/decision_engine.py                     — thresholds + calibration cache
realtime_native/bundle.py                       — model loader
realtime_native/inference.py                    — /predict/realtime-native
realtime_native/feature_builder.py              — 16 features (DB → CSV → Supabase fallback)
services/snapshot_refresh.py                    — snapshot builder (subprocess + Supabase fallback)
poskobanjir/main.py                             — scraper (graceful degradation)
artifacts/configurations/calibration_cache.json — ECE cache (dibaca tiap startup)
artifacts/production/catalog.json               — path registry (sudah dikoreksi)
models/realtime_native_bundle/manifest.json     — model bundle manifest
data/processed/realtime_feature_history.csv     — temporal features CSV fallback (1,406 rows)
frontend/src/lib/floodAgent.js                  — chat + offline KB (10 topik)
frontend/src/hooks/useFloodRisk.js              — polling /predict/realtime-native
frontend/src/components/FloodMap.jsx            — peta 5 kotamadya (bias BPBD)
frontend/src/styles.css                         — semua CSS
frontend/.env.local                             — VITE_API_BASE_URL untuk lokal (gitignored)
```

---

## Notes untuk Claude

- **Scikit-learn versi**: bundle dilatih dengan sklearn **1.8.0**, bukan 1.5.2 (info lama di README sudah tidak valid)
- **`FEATURE_HISTORY_DB_ENABLED=false`** ada di `.env` — ini **sengaja** (DB lokal tidak tersambung). Jangan hapus
- **`DB_PERSISTENCE_ENABLED=false`** ada di `.env` — ini **sengaja**, pipeline tidak coba tulis ke DB lokal
- **Zone 0 di dashboard** bukan error — tidak ada banjir. Probability < 1% sekarang tampil sebagai 1
- **`apscheduler`** wajib terinstall lokal: `pip install apscheduler`
- **Supabase connection timeout** dari lokal adalah normal — Fly.dev deployment tersambung langsung
- **Frontend build check**: `cd frontend && npm run build` harus clean sebelum push
- **BMKG alerts filtered out = 0** adalah benar jika semua alert untuk luar Jakarta (Sulawesi, dll)
- **`VITE_API_BASE_URL`** harus di `frontend/.env.local` untuk lokal, atau Vercel dashboard untuk production. Root `.env` tidak dibaca Vite
- **Snapshot fallback chain**: local file → Supabase DB → empty snapshot (terakhir)
- **`/readyz`** akan 503 di lokal karena coba konek Supabase — normal, bukan error kode
- **`FLOOD_API_KEYS=demo123`** adalah kunci untuk `/predict/agentic`, bukan untuk endpoint publik frontend
