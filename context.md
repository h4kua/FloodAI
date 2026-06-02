# deFlood.ai — Project Context

> Last updated: 2026-06-02 (rev2). Update this file whenever architecture, known issues, or deployment state changes.

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
| Backend API | FastAPI + Uvicorn, port 8080 | Railway |
| Frontend | React 18 + Vite 5 | Vercel |
| Database | Supabase / PostgreSQL | Supabase (ap-south-1) |
| ML Runtime | XGBoost 3.2.0 + scikit-learn 1.8.0 | bundled di Railway |
| AI Chat | Groq API (llama-3.3-70b-versatile) | via Railway env |
| Map | React-Leaflet + OpenStreetMap | client-side |
| Geocoding | Nominatim / OSM + OSRM routing | public API |

### Run lokal

```bash
# Backend
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload

# Frontend
cd frontend && npm run dev
```

### Env vars wajib (lihat .env.example)
- Backend: `GROQ_API_KEY`, `DATABASE_URL`, `DB_HOST/PORT/NAME/USER/PASSWORD`, `FLOOD_API_KEYS`, `OPENWEATHER_API_KEY`
- Frontend: `VITE_API_BASE_URL=https://your-backend.railway.app`

---

## Arsitektur Backend

```
api/
  main.py              — FastAPI app, APScheduler (refresh snapshot tiap 15 menit)
  routes/
    chat.py            — POST /api/chat (Groq LLM)
    agentic_llm.py     — POST /predict/agentic (5-stage pipeline)
  observability.py     — logging, metrics, middleware
  security.py          — API key auth

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
  inference.py         — GET /predict/realtime-native (endpoint utama frontend)
  feature_builder.py   — build 16 features dari snapshot (DB + CSV fallback)
  training.py          — retrain model

services/
  decision_engine.py   — threshold logic, calibration cache reader
  snapshot_refresh.py  — build fresh snapshot dari semua sumber data
  shelter_locator.py   — haversine nearest shelter
  bnpb_jakarta_mapper.py — kecamatan → kabkot mapping
  bmkg_filter.py       — filter BMKG alerts hanya untuk Jakarta
  ... (30+ service files)

db/
  psycopg2_connection.py — ThreadedConnectionPool ke Supabase PostgreSQL
  snapshot_repository.py — save/load realtime snapshot ke DB
  supabase_client.py     — lazy HTTP client (fallback jika psycopg2 gagal)

poskobanjir/
  main.py              — scraper pipeline (GRACEFUL DEGRADATION sejak fix)
  services/fetcher.py  — fetch XML dari poskobanjir.dsdadki.web.id
  processing/cleaner.py

evaluation/
  calibration.py       — compute ECE, Brier score
  metrics.py, scenario_runner.py

scripts/
  process_bpbd.py               — proses CSV BPBD → flood calendar + zone frequency
  run_calibration_from_bpbd.py  — kalibrasi ulang model dari data BPBD
```

---

## Arsitektur Frontend

```
frontend/src/
  App.jsx              — shell: topbar (68px), nav, theme/lang toggle
  styles.css           — semua CSS (design tokens, responsive, overflow-x hidden)
  pages/
    Home.jsx           — Command Center: 4 metrics, peta, zone table, chatbot
    Alert.jsx          — Evacuation: address input, OSRM route, shelter locator
    About.jsx          — tech info, disclaimer, LinkedIn + Instagram links
  components/
    ChatBot.jsx        — floating chatbot FAB (offline KB fallback built-in)
    FloodMap.jsx       — Leaflet peta DKI Jakarta + risk overlay
    EvacuationMap.jsx  — peta rute evakuasi
  hooks/
    useFloodRisk.js    — polling /predict/realtime-native tiap 15 menit
    useChat.js         — state management chat history
  lib/
    floodAgent.js      — kirim ke /api/chat + OFFLINE KB fallback (6 topik, ID+EN)
    translations.js    — semua string bilingual ID/EN
    appContext.jsx      — React context: lang + theme
```

### Fitur Frontend
- Dark/light theme, persisted localStorage
- Bilingual ID/EN, auto-detect dari pesan chatbot
- 4 metric cards (zona siaga, warga terdampak, skor risiko, curah hujan)
- Zone table 5 zona dengan bias data-driven BPBD
- TMA label `○ est.` (estimasi), Rainfall label `● real` (OpenWeather)
- Chatbot offline KB: evakuasi, status, tanda banjir, shelter, kontak, dokumen
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
| **ECE (calibration)** | **0.1962** (n=1,391) — dikalibrasi ulang dari BPBD 2024-2026 |
| Brier score | 0.103 |
| Training records | 2,928 Jakarta 2013-2026 |

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
- Python 3.12.10 · sklearn 1.8.0 · xgboost 3.2.0 · joblib 1.4.2 · numpy 1.26.4

---

## Data Sources

### Realtime
| Sumber | Data | Status |
|---|---|---|
| `poskobanjir.dsdadki.web.id/xmldata.xml` | TMA sungai Jakarta | **OFFLINE** — server DSDADKI mati |
| OpenWeather API | curah hujan, suhu, kelembapan | OK |
| BMKG nowcast feed | alert cuaca ekstrem | OK (filter Jakarta saja) |

> Ketika TMA offline: pipeline graceful degrade, OpenWeather + BMKG tetap jalan. TMA di frontend ditampilkan sebagai `○ est.` (estimasi dari risk score).

### Historical / Static
| File | Isi |
|---|---|
| `data/raw/bpbd_banjir_2024.csv` | BPBD kejadian banjir Jakarta 2024 |
| `data/raw/bpbd_banjir_2025_2026.csv` | BPBD 2025 Q1-Q3 + 2026 Q1 |
| `data/raw/data_banjir_combine_final.csv` | Dataset training 2013-2026 |
| `data/processed/bpbd_flood_calendar.csv` | Quarterly flood flag dari BPBD |
| `data/processed/zone_flood_frequency.csv` | Event count per zona → sumber zone biases |
| `data/processed/calibration_labeled.csv` | 1,391 labeled rows untuk kalibrasi ECE |
| `data/processed/realtime_feature_history.csv` | 1,406 rows riwayat temporal features (CSV fallback) |
| `artifacts/configurations/calibration_cache.json` | ECE 0.1962, Brier 0.103, n=1,391 |
| `models/realtime_native_bundle/` | Model bundle: pkl, json, manifest |

---

## Zone Biases (data-driven BPBD)

| Zona | Wilayah | Bias | BPBD Events |
|---|---|---|---|
| Kebayoran | Jakarta Selatan | **+20** | 239 — paling sering banjir |
| Penjaringan | Jakarta Utara | +6 | 158 |
| Jatinegara | Jakarta Timur | +6 | 157 — OOD flag |
| Kalideres | Jakarta Barat | +4 | 144 |
| Cengkareng | Jakarta Barat | -1 | 114 |

> Bias lama hardcoded salah besar: Kebayoran di-set -22 (diasumsikan paling aman), padahal event count BPBD tertinggi. Sudah dikoreksi.

---

## Known Issues

### SELESAI ✅
| Issue | Fix |
|---|---|
| TMA scraper abort pipeline | Graceful degradation — tiap sumber dibungkus try/except |
| ECE 0.38 n=7 | Dikalibrasi ulang → ECE 0.20 n=1,391 dari data BPBD |
| Calibration cache path bug | `"..", ".."` → `".."` di `decision_engine.py` |
| Temporal features selalu 0 | `FEATURE_HISTORY_DB_ENABLED=false` + DB timeout → CSV fallback di `feature_builder.py` |
| Duplicate `_append_history` | Dead code dihapus |
| Zone biases salah | Data-driven dari BPBD (Kebayoran -22 → +20) |
| Chatbot "AI tidak tersedia" | Offline KB fallback 6 topik ID+EN di `floodAgent.js` |
| Risk score tampil 0 | Probabilitas < 1% sekarang tampil sebagai 1 |
| Navbar terlalu kecil | Topbar 58px → 68px, logo lebih besar |
| Mobile horizontal scroll | `overflow-x: hidden` pada html/body, breakpoints diperketat |
| About page tanpa LinkedIn | Tombol LinkedIn (juanjaviersz) ditambahkan |
| `frontend/.env.example` salah var | `VITE_API_URL` → `VITE_API_BASE_URL` |
| `apscheduler` missing lokal | `pip install apscheduler` |

### MASIH OPEN ⚠️
| Issue | Keterangan |
|---|---|
| TMA sensor DSDADKI offline | Server fisik mati, bukan kode. TMA masih estimasi sampai DSDADKI aktif kembali |
| Zone data masih estimasi | 5 zona derived dari 1 ML score + bias, bukan sensor per-kecamatan. Fix butuh sensor DSDADKI |
| BNPB kecamatan write-back | Mapping kota → kecamatan reverse belum fully populated di pipeline output |
| DB lokal timeout | Supabase hanya tersambung dari Railway/Fly.dev, bukan lokal. CSV fallback aktif |

### SELESAI (batch 2) ✅
| Issue | Fix |
|---|---|
| catalog.json path stale | Path `app/` prefix dihapus — sekarang `services/prediction_service.py`, `api/main.py`, dll |
| Chatbot offline KB terbatas | Expanded dari 6 → 10 topik: cuaca, pasca banjir, prediksi, pompa |
| Snapshot fallback saat TMA+OW offline | `snapshot_refresh.py` coba Supabase cache sebelum return empty snapshot |
| Snapshot file missing (fresh clone) | `feature_builder.py` fallback ke Supabase sebelum raise FileNotFoundError |
| Frontend tidak bisa konek backend lokal | `frontend/.env.local` dibuat dengan `VITE_API_BASE_URL=http://localhost:8080` |
| FloodMap bias salah (Jakarta Selatan -18) | Di-fix ke +18 sesuai BPBD data — sekarang konsisten dengan zone table |
| `evac.searching` translation key hilang | Ditambahkan di `translations.js` (ID+EN) |
| ChatBot quick replies hanya 3 | Diperluas ke 6 quick replies dengan translation keys baru |
| `useChat.js` loading macet jika error | Ditambahkan try/catch/finally sehingga loading selalu di-reset |
| `psycopg2_connection.py` indentasi jelek | `get_psycopg2_connection()` diformat ulang, DSN dipisah ke variabel |

---

## Key Paths

```
api/main.py                                     — FastAPI entry point
services/decision_engine.py                     — thresholds + calibration cache
realtime_native/bundle.py                       — model loader
realtime_native/inference.py                    — /predict/realtime-native
realtime_native/feature_builder.py              — 16 features (DB + CSV fallback)
poskobanjir/main.py                             — scraper (graceful degradation)
artifacts/configurations/calibration_cache.json — ECE cache (dibaca tiap startup)
models/realtime_native_bundle/manifest.json     — model bundle manifest
data/processed/realtime_feature_history.csv     — temporal features CSV fallback (1,406 rows)
frontend/src/lib/floodAgent.js                  — chat + offline KB
frontend/src/hooks/useFloodRisk.js              — polling backend
frontend/src/styles.css                         — semua CSS
```

---

## Notes untuk Claude

- **Scikit-learn versi**: bundle dilatih dengan sklearn **1.8.0**, bukan 1.5.2 (info lama di README sudah tidak valid)
- **`FEATURE_HISTORY_DB_ENABLED=false`** ada di `.env` — ini **sengaja** (DB lokal tidak tersambung). Jangan hapus. Fallback CSV sudah diimplementasikan
- **Zone 0 di dashboard** bukan error — memang tidak ada banjir. `probability 0.32%` rounds ke 0, sekarang tampil sebagai 1
- **`apscheduler`** wajib terinstall lokal: `pip install apscheduler`
- **Supabase connection timeout** dari lokal adalah normal — Railway/Fly.dev deployment tersambung langsung
- **Frontend build check**: `cd frontend && npm run build` harus clean sebelum push
- **BMKG alerts filtered out = 0** adalah benar jika semua alert untuk luar Jakarta (Sulawesi, dll)
- **`_CALIBRATION_CACHE` path**: `services/decision_engine.py` — harus satu level `".."` dari `services/`, bukan dua
- **`VITE_API_BASE_URL`** untuk Vite harus ada di `frontend/.env` atau `frontend/.env.local`, BUKAN di root `.env`. Root `.env` hanya dibaca backend Python. Untuk lokal: `http://localhost:8080`. Untuk Vercel: set di dashboard Vercel.
- **Backend deploy URL**: root `.env` punya `VITE_API_BASE_URL=https://floodai.fly.dev` → backend di Fly.dev (bukan Railway lagi)
- **Snapshot fallback**: jika `poskobanjir/data/clean/realtime_snapshot.json` tidak ada (fresh clone), `feature_builder.py` otomatis coba load dari Supabase
