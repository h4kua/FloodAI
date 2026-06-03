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
| Deploy | Fly.io (backend) · Vercel (frontend) |

---

## Run

```bash
# Backend
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload

# Frontend — dev mode, Vite proxy (VITE_API_BASE_URL tidak perlu diset)
cd frontend && npm run dev

# Refresh snapshot manual (scheduler otomatis tiap 15 menit)
cd poskobanjir && python main.py
```

---

## Key paths

| Path | Fungsi |
|---|---|
| `api/main.py` | FastAPI app, CORS middleware, scheduler, semua endpoints |
| `api/routes/chat.py` | `POST /api/chat` (Groq chatbot, tanpa auth) |
| `api/routes/agentic_llm.py` | `POST /predict/agentic/explain` |
| `api/routes/crew_analysis.py` | `POST /predict/crew-analysis` (CrewAI) |
| `api/security.py` | `require_api_key` dependency + deque-backed rate limiting |
| `pipeline/flood_pipeline.py` | Orchestrator 5-stage pipeline |
| `services/decision_engine.py` | Canonical decision authority (L0–L4 hierarchy) |
| `services/snapshot_refresh.py` | Build snapshot baru via subprocess poskobanjir |
| `realtime_native/feature_builder.py` | Build 16 fitur dari snapshot + `stations_summary` (real DSDADKI readings) |
| `realtime_native/inference.py` | `GET /predict/realtime-native` — exposes `stations[]` dan `snapshot_fetched_at` |
| `db/psycopg2_connection.py` | Connection pool + `pooled_connection()` context manager |
| `poskobanjir/main.py` | Pipeline scraper: TMA JSON → OpenWeather → BMKG → snapshot JSON |
| `poskobanjir/services/parser.py` | Parse TMA JSON/XML, BMKG CAP, cuaca.json (timezone-aware) |
| `poskobanjir/data/clean/realtime_snapshot.json` | Snapshot aktif (diupdate tiap 15 menit) |
| `frontend/src/pages/Home.jsx` | Command center — metrics, peta, stasiun TMA, zona risiko |
| `frontend/src/components/FloodMap.jsx` | Peta Leaflet — real DSDADKI sensor markers + district reference |
| `frontend/src/hooks/useFloodRisk.js` | Poll `GET /predict/realtime-native` tiap **5 menit** |
| `frontend/src/lib/translations.js` | Semua teks ID + EN |
| `frontend/src/lib/floodAgent.js` | Chat backend call + offline KB fallback |
| `frontend/vite.config.js` | Dev proxy `/predict/*` dan `/api/*` → port 8080 |

---

## Endpoints

| Endpoint | Auth | Deskripsi |
|---|---|---|
| `GET /predict/realtime-native` | — | XGBoost inference dari snapshot; returns `stations[]`, `snapshot_fetched_at` |
| `POST /predict/agentic` | X-Api-Key | Full 5-stage agentic pipeline |
| `POST /predict/agentic/explain` | X-Api-Key | Pipeline + LLM explanation (Bahasa Indonesia) |
| `POST /predict/crew-analysis` | X-Api-Key | Pipeline + CrewAI 3-agent analysis |
| `POST /api/chat` | — | Groq chatbot bilingual (ID/EN), cache client module-level |
| `GET /api/chat/health` | — | Cek apakah GROQ_API_KEY terkonfigurasi |
| `GET /healthz` | — | Liveness check + scheduler status |
| `GET /readyz` | — | Readiness check (DB + thresholds) |
| `GET /metrics` | — | Prometheus metrics |
| `POST /internal/refresh-snapshot` | X-Internal-Secret | Rate-limited manual snapshot refresh (min 5 menit antar request) |

---

## `/predict/realtime-native` response shape

Field penting yang digunakan frontend:

```jsonc
{
  "risk_level": "WARNING",           // SAFE | WARNING | DANGER
  "probability": 0.35,
  "risk_interpretation": "...",
  "recommended_action": ["...", "..."],
  "snapshot_fetched_at": "2026-06-03T05:45:00+00:00",  // kapan data sensor diambil
  "bmkg_forecast": [...],
  "ood_detection": { "is_outlier": false, "score": 0.12 },
  "features": {
    "rainfall_mm": 0.0,
    "water_level_ratio": 0.82,       // real dari sensor DSDADKI
    "water_level_delta": 0.02,       // perubahan 15-menit terakhir
    "humidity_pct": 57.0,
    "temperature_c": 34.0,
    "monsoon_season": 0              // 1 = Nov–Mar
  },
  "diagnostics": {
    "water_level_records": 37,       // jumlah stasiun aktif
    "rainfall_acc_3h": 0.0,
    "rainfall_acc_6h": 0.0,
    "rainfall_trend_mm_h": 0.0,
    "trend_state": {
      "risk_trend": "stable",        // increasing | decreasing | stable
      "anomaly_detected": false,
      "anomaly_type": null           // spike | slow_accumulation | null
    },
    "stations_summary": [...]        // lihat bagian Data: stations_summary
  },
  "stations": [...]                  // alias dari stations_summary, untuk frontend
}
```

---

## Data: `stations_summary` / `stations[]`

Dibangun di `realtime_native/feature_builder.py`, dikirim di `inference.py` sebagai `stations`.

Berisi **semua stasiun DSDADKI yang valid** (kalibrated, bukan pompa, siaga1 > 0), diurutkan ratio tertinggi dulu, max 20 entri.

```jsonc
{
  "nama": "P.A. Karet 1",
  "lokasi": "Kebayoran Lama",
  "tinggi_air": 332.0,          // cm, dari sensor real
  "siaga1": 400.0,              // ambang siaga-1
  "siaga2": 350.0,
  "siaga3": 320.0,
  "ratio": 0.830,               // tinggi_air / siaga1
  "status_siaga": "Siaga 3",    // string asli dari DSDADKI
  "lat": -6.2234,               // null jika tidak ada/invalid
  "lon": 106.8015               // null jika tidak ada/invalid
}
```

**Stasiun yang TIDAK masuk:**
- Stasiun pompa (nama mulai "POMPA") — threshold-nya operasional bukan banjir
- Stasiun tidak terkalibrasi (siaga1 = siaga2 = siaga3)
- Koordinat di luar Jakarta bounds (-6.6…-5.8 lat, 106.4…107.2 lon) → lat/lon = null

---

## Decision hierarchy (`services/decision_engine.py`)

```
L0 PHYSICAL    — input tidak valid → UNKNOWN
L1 SIAGA       — water_level_ratio ≥ 0.90 → DANGER (override ML)
L1.5 MULTI     — ≥2 sinyal kuat (rainfall≥60mm, WLR≥0.85, bmkg≥0.80) → DANGER
L1.7 BMKG      — BMKG certainty "Observed" + severity "Extreme" → WARNING floor
L1.8 HYDRO     — post-ML: WLR ≥ 0.75 → minimum WARNING
L1.9 OOD       — IsolationForest outlier → WARNING floor (tapi disupress jika WLR≥0.75)
L2 INTEGRITY   — failure severe → escalate 1 level
L3 ML          — XGBoost probability vs adaptive threshold
L4 TREND       — tren naik sustained → WARNING→DANGER
```

**OOD suppression:** `is_outlier` di-suppress di backend ketika `water_level_ratio >= 0.75` (model dilatih saat TMA data rusak → WLR tinggi bukan anomali nyata). Frontend juga cek `waterLevelRatio < 0.75` sebelum tampil badge OOD.

**Pump station exclusion:** Stasiun "POMPA*" dikecualikan dari `water_level_ratio` karena threshold-nya adalah kapasitas operasional pompa, bukan threshold banjir publik.

---

## Frontend: Command Center (`Home.jsx`)

### Data yang 100% real dari API

| UI Element | Data source |
|---|---|
| **STASIUN SIAGA count** | `stations.filter(s => s.ratio >= 1.0/0.75).length` |
| **STASIUN TMA AKTIF count** | `diagnostics.water_level_records` |
| **SKOR RISIKO** | `probability × 100` dari XGBoost |
| **CURAH HUJAN** | `features.rainfall_mm` dari OpenWeather |
| **MUKA AIR %** + arrow ↑/↓ | `features.water_level_ratio` + `water_level_delta` |
| **Alert Panel** | `stations[]` dengan ratio ≥ 0.75 (nama & TMA nyata) |
| **StationPanel** | Full tabel semua `stations[]` dari DSDADKI |
| **Peta — titik sensor** | `stations[]` dengan lat/lon valid |
| **Akum. 3j/6j** | `diagnostics.rainfall_acc_3h/acc_6h` |
| **Tren Hujan** | `diagnostics.rainfall_trend_mm_h` |
| **Anomali** badge | `trend_state.anomaly_detected/type` |
| **Musim Hujan** chip | `features.monsoon_season` |
| **BMKG alert** count | `diagnostics.bmkg_alerts_total` |
| **BMKG forecast** panel | `bmkg_forecast[]` dari cuaca.json |
| **"Data sensor HH:MM WIB"** | `snapshot_fetched_at` (UTC→WIB +7) |

### Data estimasi / ML (bukan sensor langsung)

| UI Element | Keterangan |
|---|---|
| **Peta — district circles** | Referensi geografis saja (sangat samar, dashed) — bukan data |
| **Zone table (5 baris)** | Estimasi per-zona: `tma_base × (real_WLR + bias/200)` — TMA pakai WLR real tapi tma_base hardcoded |
| **Probabilitas zona** | `(riskScore + zone_bias) / 100` — satu ML score + bias historis |
| **Agent Panel** | Simulasi (label "simulasi") |

### Polling interval
- Auto-refresh: **5 menit** (`POLL_INTERVAL_MS = 5 * 60 * 1000`)
- Manual: tombol REFRESH
- Backend scheduler: tiap 15 menit (env `SNAPSHOT_REFRESH_INTERVAL_MINUTES`)

---

## Frontend: Peta (`FloodMap.jsx`)

**Layer 1 — Real sensor markers (foreground):**
- Sumber: `stations[]` dari API, hanya yang `lat != null && lon != null`
- Warna: `stationColor(ratio)` → merah ≥1.0, oranye ≥0.75, kuning ≥0.50, hijau
- Popup: nama stasiun, TMA cm, threshold siaga-1, ratio%

**Layer 2 — District reference (background, sangat samar):**
- `fillOpacity: 0.04` saat ada sensor, `0.14` jika tidak ada sensor
- Popup menjelaskan ini bukan data sensor

---

## Backend bug fixes yang penting (session ini)

### `db/psycopg2_connection.py`
- `override=True` → `override=False` di `load_dotenv` (Fly.io env vars tidak ditimpa .env lokal)
- Password URL-encoded di DSN string (`urllib.parse.quote`) — password dengan karakter special (@#?) tidak lagi rusak koneksi
- `pooled_connection()` sekarang rollback transaction pada exception sebelum return ke pool — mencegah open transaction bocor ke caller berikutnya

### `api/main.py`
- `_get_idempotent_response` / `_store_idempotent_response` sekarang catch DB errors (DB down tidak lagi crash seluruh `/predict/agentic`)
- `_request_budget_s()` ValueError fallback `15.0` → `60.0` (konsisten dengan minimum `30.0`)

### `api/security.py`
- Hapus duplicate import
- `_buckets` dict prune entri kosong (mencegah memory leak untuk key tidak aktif)

---

## CrewAI (`agents/crew/flood_crew.py`)

3 agen sekuensial setelah ML pipeline:

```
AhliCuaca → AhliHidrologi → KoordinatorRisiko
```

- Model: `groq/llama-3.3-70b-versatile` via litellm
- Timeout: 45s total (`CREW_TIMEOUT_S`), 20s per HTTP call
- Fallback deterministik jika crew gagal
- Output: `status_banjir`, `penjelasan`, `tindakan`, `populasi_terdampak`, `tingkat_kepercayaan`, `pesan_petugas`, `analisis_cuaca`, `analisis_hidrologi`

---

## Chat (`api/routes/chat.py`)

- Groq client: **module-level singleton** — tidak buat HTTP pool baru per request
- Timeout: 25s (Groq SDK `timeout=25.0`)
- Frontend timeout: 25s AbortController di `floodAgent.js`
- Fallback offline: keyword matching ke `OFFLINE_KB` dict (tanpa network)
- Status indicator: `aiOnline=null` → "Menghubungkan...", `true` → "AI Online", `false` → "Offline (KB)"

---

## Known issues

| Issue | Status | Dampak |
|---|---|---|
| Stasiun DSDADKI tanpa GPS | Aktif | Beberapa stasiun `lat/lon = null` → tidak muncul di peta, tapi tetap masuk StationPanel dan alert |
| Calibration ECE 0.196 | Aktif | Confidence score masih kurang akurat (target < 0.10) |
| BNPB district mapping gap | Aktif | Beberapa kecamatan tidak ter-map ke kabkot |
| Zone table tma_base hardcoded | By design | TMA pakai real WLR tapi tma_base per-zona masih konstanta; tidak ada per-zona sensor breakdown dari DSDADKI API |

---

## Environment variables

```bash
# .env (project root — wajib)
FLOOD_API_KEYS=demo123              # comma-separated; random string di production
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile
LLM_PROVIDER=groq                   # groq | anthropic
OPENWEATHER_API_KEY=...
SUPABASE_URL=...
SUPABASE_KEY=...
DB_HOST=...
DB_PASSWORD=...                     # URL-encoded otomatis, aman dengan karakter spesial
DB_NAME=flood_ai
DB_USER=postgres

SNAPSHOT_REFRESH_INTERVAL_MINUTES=15   # default 15, range 1–60
CREW_TIMEOUT_S=45
INTERNAL_SECRET=...                    # untuk /internal/refresh-snapshot

# frontend/.env.local (jangan dicommit)
VITE_API_BASE_URL=                  # kosong = Vite proxy (dev)
                                    # https://your-backend.railway.app (production)
```

---

## Recent commits

```
aad22c9 feat: replace fake map circles with real DSDADKI sensor markers
d18e2c9 fix: add parentheses around ?? and || to satisfy esbuild precedence rule
3a0fe4b feat: replace all fake/derived data with real DSDADKI sensor readings
a331613 feat: wire all real-time sensor data into frontend UI
fb90090 fix: real-time data freshness — 5-min polling, sensor timestamp, fix misleading TMA note
1979b2e fix: backend bug fixes — DB pool safety, DSN encoding, security, idempotency
8d0351d fix: focus both maps strictly on DKI Jakarta
7b4fed0 fix: 6 bugs — timezone, chatbot state, timeouts, Groq client, refresh UX
cdc8d8f fix: exclude pump stations from water_level_ratio calculation
```
