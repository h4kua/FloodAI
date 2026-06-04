# deFlood.ai — Project Context

> Last updated: 2026-06-04. Update this file whenever architecture, known issues, or deployment state changes.

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI + uvicorn, port 8080 |
| Frontend | React 18 + Vite, port 5173 (dev) |
| Database | Supabase / PostgreSQL (psycopg2) |
| ML | XGBoost + scikit-learn 1.5.2 (AUC ~0.94, ECE 0.196) |
| LLM | Groq llama-3.3-70b-versatile (chatbot + explain) |
| Deploy | Railway (backend) · Vercel (frontend) |

---

## Run

```bash
# Backend
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload

# Frontend (dev, Vite proxies /predict/* and /api/* to port 8080)
cd frontend && npm run dev

# Manual snapshot refresh
cd poskobanjir && python main.py
```

---

## Key paths

| Path | Fungsi |
|---|---|
| `api/main.py` | FastAPI app, CORS, scheduler, semua endpoints |
| `api/routes/chat.py` | `POST /api/chat` — Groq chatbot, module-level client, max_tokens 2000, timeout 28s |
| `api/routes/agentic_llm.py` | `POST /predict/agentic/explain` |
| `api/security.py` | `require_api_key` + deque-based rate limiting |
| `realtime_native/inference.py` | `GET /predict/realtime-native` — main ML endpoint, builds `wilayah_summary` |
| `realtime_native/feature_builder.py` | 16 fitur dari snapshot + `stations_summary` (DSDADKI readings) |
| `poskobanjir/main.py` | Scraper: TMA JSON → OpenWeather → BMKG → snapshot JSON |
| `poskobanjir/services/parser.py` | Parse TMA JSON/XML, BMKG CAP, cuaca.json |
| `poskobanjir/data/clean/realtime_snapshot.json` | Snapshot aktif (update tiap 15 mnt) |
| `poskobanjir/data/clean/bmkg_cuaca.json` | BMKG per-wilayah forecast cache |
| `frontend/src/pages/Home.jsx` | Command center — semua komponen utama dashboard |
| `frontend/src/components/FloodMap.jsx` | Peta Leaflet — real DSDADKI sensor markers |
| `frontend/src/components/ChatBot.jsx` | Floating chatbot FAB + panel |
| `frontend/src/hooks/useFloodRisk.js` | Poll `GET /predict/realtime-native` tiap 5 menit |
| `frontend/src/lib/floodAgent.js` | Groq API call + offline KB fallback + `_matchOffline()` |
| `frontend/src/lib/translations.js` | Semua teks ID + EN |
| `frontend/src/styles.css` | Single CSS file — semua styles, dark + light theme |
| `frontend/vite.config.js` | Dev proxy `/predict/*` dan `/api/*` → port 8080 |

---

## Endpoints

| Endpoint | Auth | Deskripsi |
|---|---|---|
| `GET /predict/realtime-native` | — | XGBoost inference; returns `stations[]`, `wilayah_summary`, `snapshot_fetched_at` |
| `POST /predict/agentic/explain` | X-Api-Key | Pipeline + LLM explanation |
| `POST /api/chat` | — | Groq chatbot bilingual (ID/EN) |
| `GET /api/chat/health` | — | Cek GROQ_API_KEY configured |
| `GET /healthz` | — | Liveness check + scheduler |
| `GET /readyz` | — | Readiness check (DB + thresholds) |
| `POST /internal/refresh-snapshot` | X-Internal-Secret | Manual snapshot refresh (rate-limited, min 5 mnt) |

---

## `/predict/realtime-native` — response shape (fields used by frontend)

```jsonc
{
  "risk_level": "WARNING",             // SAFE | WARNING | DANGER
  "probability": 0.47,
  "risk_interpretation": "...",        // shown in ModelOutputCard
  "recommended_action": ["...", "..."],// shown in RecommendationsPanel fallback
  "snapshot_fetched_at": "2026-06-04T...",
  "features": {
    "rainfall_mm": 9.0,
    "water_level_ratio": 0.82,         // real DSDADKI average
    "water_level_delta": 0.02,
    "humidity_pct": 57.0,
    "temperature_c": 34.0,
    "monsoon_season": 0
  },
  "diagnostics": {
    "water_level_records": 17,         // active TMA stations (tmaStationsActive)
    "rainfall_acc_3h": 0.0,
    "rainfall_acc_6h": 0.0,
    "rainfall_trend_mm_h": 0.0,
    "bmkg_alerts_total": 0,
    "trend_state": {
      "risk_trend": "stable",          // increasing | decreasing | stable
      "anomaly_detected": false,
      "anomaly_type": null,            // spike | slow_accumulation | null
      "recent_probabilities": [0.44, 0.46, 0.47]  // sparkline data
    },
    "stations_summary": [...]
  },
  "stations": [...],                   // alias of stations_summary
  "wilayah_summary": [                 // NEW — built by _build_wilayah_summary()
    {
      "wilayah": "Jakarta Utara",
      "worst_status": "Siaga 2",       // Normal | Siaga 3 | Siaga 2 | Siaga 1
      "siaga1_count": 0,
      "siaga2_count": 1,
      "siaga3_count": 11,
      "tma_count": 12,
      "forecast": [                    // from bmkg_cuaca.json, up to 4 slots
        { "local_datetime": "...", "weather_desc": "Berawan",
          "tmin": 27, "tmax": 30, "humin": 71, "humax": 87 }
      ]
    }
    // × 5 (Pusat, Utara, Barat, Selatan, Timur)
  ],
  "bmkg_forecast": [...]               // DKI aggregate fallback
}
```

`useFloodRisk.js` maps this response to `riskData`:
- `riskData.wilayahSummary` ← `json.wilayah_summary`
- `riskData.stations` ← `json.stations`
- `riskData.waterLevelRatio` ← `json.features.water_level_ratio`
- `riskData.riskScore` ← `Math.round(json.probability * 100)`
- `riskData.level` ← probability → "aman" | "waspada" | "siaga" | "bahaya"
- `riskData.tmaStationsActive` ← `json.diagnostics.water_level_records`
- `riskData.snapshotFetchedAt` ← `json.snapshot_fetched_at`
- `riskData.trendState` ← `json.diagnostics.trend_state`

---

## `stations[]` shape

```jsonc
{
  "nama": "P.A. Karet 1",
  "tinggi_air": 5036.0,    // cm
  "siaga1": 6000.0,
  "ratio": 0.839,           // tinggi_air / siaga1
  "lat": -6.2234,           // null if unavailable/outside Jakarta bounds
  "lon": 106.8015
}
```

Excluded: stations with nama starting "POMPA" (operational threshold, not flood threshold), uncalibrated (siaga1=siaga2=siaga3), coords outside DKI bounds.

---

## Frontend: Home.jsx — Architecture

### Component tree

```
Home()
├── AlertRibbon           — real s1/s2 counts from stations[]
├── StatusHero            — level badge + buildStatusDesc() + trend pill badge + sparkline
├── MetricsRow            — 3 metric cards (all real data)
├── WilayahRainfallStrip  — current BMKG weather per 5 wilayah (dari wilayahSummary)
├── SensorStrip           — WLR, temp, humidity, acc3h/6h, trend chips
├── cmd-main grid
│   ├── FloodMap          — Leaflet with real DSDADKI sensor markers
│   └── cmd-sidebar
│       ├── AlertPanel    — stations with ratio ≥ 0.75
│       └── RecommendationsPanel  — REALTIME: sensor names, TMA readings, wilayah status
├── ModelOutputCard       — ML interpretation + signal chips (NEW)
├── StationPanel          — full DSDADKI station table (expandable)
├── ZoneCards             — 5 kota administrasi, sorted highest risk first (NEW)
└── WilayahForecastGrid   — compact 12h BMKG timeline per wilayah (NEW)
```

### Key functions in Home.jsx

| Function | What it does |
|---|---|
| `deriveWilayahZones()` | Computes flood probability for ALL 5 kota administrasi, sorted descending. Replaces old `BASE_ZONES` hardcoded sub-zones. Uses `wilayahSummary` realtime data. |
| `buildStatusDesc()` | Generates StatusHero description from realtime sensors (station names, counts, WLR%). No static strings. |
| `WILAYAH_BIAS` | Historical flood frequency bias per kota: Utara +18, Timur +10, Selatan +8, Barat +5, Pusat -5 |
| `STATUS_RISK_BONUS` | Bonus added when wilayah has active Siaga: S1 +35, S2 +22, S3 +12 |

### What's 100% realtime (real sensor data)

| UI | Source |
|---|---|
| Siaga station count | `stations.filter(ratio ≥ 1.0/0.75).length` |
| Active TMA stations | `diagnostics.water_level_records` |
| Risk score | `probability × 100` XGBoost |
| Water level % + direction | `water_level_ratio` + `water_level_delta` DSDADKI |
| Rainfall | `rainfall_mm` OpenWeather |
| Alert Panel station names + TMA | `stations[]` DSDADKI |
| StationPanel full table | `stations[]` DSDADKI |
| RecommendationsPanel text | Generated from `stations[]` + `wilayahSummary` realtime |
| StatusHero description | `buildStatusDesc()` uses station names, counts, WLR, trend |
| WilayahRainfallStrip | `wilayahSummary[].forecast[0]` (BMKG) |
| WilayahForecastGrid | `wilayahSummary[].forecast[]` (BMKG, up to 4 slots) |
| ZoneCards badge + TMA pips | `wilayahSummary[].worst_status + siaga*_count` |
| ModelOutputCard chips | `riskScore`, `waterLevelRatio`, `rainfall`, `riskTrend` |
| Sensor chips (SensorStrip) | acc3h, acc6h, trend, anomaly, OOD |

### What's estimated/ML (not direct sensor)

| UI | Note |
|---|---|
| Zone flood probability % | `40% ML score + status bonus + siaga bonus + BMKG rain + historical bias` |
| Map district circles | Reference only, very faint |

---

## Frontend: Chatbot (`floodAgent.js`)

### Architecture
- **Primary**: POST `/api/chat` → Groq llama-3.3-70b-versatile
- **Fallback**: `_matchOffline(text, lang)` → `OFFLINE_KB[lang][key]`
- **Timeout**: 28s AbortController + 28s Groq SDK timeout
- **System prompt**: `SYSTEM_PROMPT` — language rules, typo tolerance, response length, all KB data

### SYSTEM_PROMPT knowledge sections
1. Typo/informal text handling (kemaa→kemana, bnjir→banjir, etc.)
2. Response length by question type (status 2-3 kalimat; wilayah 200 kata; darurat 60 kata)
3. Jakarta flood geography by kecamatan (RT/RW numbered ranges)
4. **Nama jalan per wilayah** (50+ street names: Jl. Pluit Raya, Jl. Daan Mogot, Jl. Kampung Melayu Besar, dll.) — added 2026-06-04
5. **Kali/sungai** utama (Ciliwung, Angke, Pesanggrahan, Sunter, Cakung, Sekretaris)
6. **Infrastruktur** (SODETAN Ciliwung, BKB, BKT, 600+ pompa, waduk Pluit/Sunter/Ria Rio)
7. **5 kota administrasi** clarification (Jakarta bukan kabupaten biasa, hanya Kep. Seribu yg kabupaten)
8. Flood duration table (kilat 2-6h; Katulampa Siaga 1/2/3 → hours)
9. Shelter addresses with jalan names per wilayah
10. Landmark flood status (malls, RS, sekolah as posko)
11. Distance estimates shelter (km + minutes)
12. Website feature explanation

### OFFLINE_KB keys
`evakuasi` | `status` | `wilayah` | `tanda` | `shelter` | `kontak` | `durasi` | `dokumen` | `cuaca` | `pasca` | `prediksi` | `pompa` | `web` | `rtrw` | `landmark` | `jarak` | **`jalan`** (added 2026-06-04)

### `_matchOffline()` routing order
```
jalan     → jl./jalan/kali/sungai/kawasan/komplek
website   → ini apa/cara pakai/fitur/explain
durasi    → berapa lama/kapan surut/katulampa
jarak     → berapa jauh/km dari/menit dari
landmark  → mall/rs/rumah sakit/sekolah/sdn
rtrw      → \brt\b/\brw\b/rt 0/rw 0
wilayah   → kecamatan/kelurahan/daerah
evakuasi  → kemana/harus kemana/tas darurat/langkah
status    → kondisi/sekarang/aman
...
```

---

## Frontend: CSS (`styles.css`)

### Design system
- Dark theme: `--bg: #111827` (slate), `--panel: #1a2338`, `--panel-2: #1e2d47`
- Light theme: `--bg: #f0ede8` (warm cream), `--panel: #faf9f7`
- Elevation: panel < panel-2 < panel-3
- Type: Inter (body), Space Grotesk (display), JetBrains Mono (data/code)

### Key CSS blocks added in this session
| Class | Purpose |
|---|---|
| `.rainfall-strip` | Full-width per-wilayah BMKG cards (desktop: min-height 148px, 2.25rem icon) |
| `.rain-card` | Individual wilayah weather card |
| `.forecast-compact-grid/row/slot` | 12h BMKG forecast timeline (compact 82px slots) |
| `.fcs-*` | Forecast compact slot sub-elements |
| `.model-output-card` | ML analysis card with cyan border-left and signal chips |
| `.model-signal-chip` | Individual signal chip (Skor, Status, Muka Air, Hujan, Tren) |
| `.forecast-rain-alert` | 🌧 pill showing when rain arrives |
| `.wilayah-status-badge` | Status pill for each kota administrasi |
| `.wilayah-siaga-pip` | Small S1/S2/S3 count badge |

### Mobile chatbot fix
```css
/* @media max-width: 640px */
.chatbot-panel {
  position: fixed;          /* was: position: absolute with broken max-width:100% */
  bottom: 76px;
  left: 0.625rem;
  right: 0.625rem;          /* spans full viewport width properly */
  width: auto;
  max-width: none;
  height: 78vh;
  max-height: 520px;
}
```

The old `position: absolute; right: 0; width: calc(100vw - 1rem); max-width: 100%` was broken because `max-width: 100%` resolved to the FAB button width (~52px), collapsing the panel.

---

## Decision hierarchy (`services/decision_engine.py`)

```
L0 PHYSICAL    — invalid input → UNKNOWN
L1 SIAGA       — WLR ≥ 0.90 → DANGER (override ML)
L1.5 MULTI     — ≥2 strong signals → DANGER
L1.7 BMKG      — Observed+Extreme → WARNING floor
L1.8 HYDRO     — WLR ≥ 0.75 → minimum WARNING
L1.9 OOD       — IsolationForest outlier → WARNING floor (suppressed if WLR ≥ 0.75)
L2 INTEGRITY   — failure severe → escalate 1 level
L3 ML          — XGBoost vs adaptive threshold
L4 TREND       — sustained rising trend → WARNING → DANGER
```

---

## Known issues

| Issue | Status | Dampak |
|---|---|---|
| DSDADKI stations without GPS | Active | Some stations lat/lon=null; appear in StationPanel/Alert but not map |
| Calibration ECE 0.196 | Active | Confidence score less accurate (target <0.10); calibration step deactivated |
| BNPB district mapping gap | Active | Some kecamatan not mapped to kabkot |
| TMA scraper sometimes broken | Active | Snapshot may be stale; StaleDataBanner shows if >30 min old |
| wilayah_summary only has BMKG forecast slots every ~6h | By design | WilayahForecastGrid time labels rounded to nearest 3/6h |

---

## Environment variables

```bash
# .env (project root)
FLOOD_API_KEYS=demo123
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile
OPENWEATHER_API_KEY=...
SUPABASE_URL=...
SUPABASE_KEY=...
DB_HOST=...
DB_PASSWORD=...
DB_NAME=flood_ai
DB_USER=postgres
SNAPSHOT_REFRESH_INTERVAL_MINUTES=15
INTERNAL_SECRET=...

# frontend/.env.local
VITE_API_BASE_URL=   # empty = Vite proxy (dev); https://... in production
```

---

## Recent commits

```
ec92004 feat: model output card, compact forecast grid, sorted wilayah zones, trend badge
4944d28 feat: realtime risk zones, 12h forecast grid, dynamic hero text, chatbot streets
dd56ffe feat: per-wilayah rainfall strip + deep chatbot KB upgrade
fd568db fix: logo + rainfall per-wilayah + forecast readable + chatbot short
b11a6e1 feat: per-wilayah Jakarta conditions + abstract logo + chatbot
bf50558 feat: AI-style logo
3d4c933 feat: new TMA gauge logo + navbar
3235847 fix: tour cleanup + mobile floating card + responsiveness
```

---

## Session summary — what changed 2026-06-04

### Architecture changes
- **`deriveWilayahZones()`** replaces `BASE_ZONES` sub-zones: all 5 kota administrasi, sorted by risk
- **`buildStatusDesc()`**: StatusHero description generated from live sensors (no static strings)
- **`ModelOutputCard`**: proper ML analysis card with signal chips (replaces text strip)
- **`WilayahForecastGrid`**: compact 12h BMKG timeline (replaces WilayahGrid with sparse cards)
- **`RecommendationsPanel`**: fully realtime — station names, TMA values, wilayah status in text

### Bug fixes
- Mobile chatbot `position: fixed` fix — panel was collapsing to 52px due to broken `max-width: 100%` on absolute child of fixed parent
- Rainfall strip cards too small on desktop — increased to `min-height: 148px`, `2.25rem` icon, `0.82rem` desc
- Trend indicator "Tren 3 titik" → "Skor ~45 mnt" + pill badge with hint text
- Zone cards showed only Kebayoran/Penjaringan/Jatinegara/Kalideres/Cengkareng (Jakarta Pusat missing) → fixed

### Chatbot enrichment
- 50+ nama jalan (Jl. Pluit Raya, Jl. Daan Mogot, Jl. Kampung Melayu Besar, Jl. Dr. Saharjo, etc.)
- Kali/sungai names (Ciliwung, Angke, Pesanggrahan, Sunter, Cakung, Sekretaris)
- Infrastruktur (SODETAN, BKB/BKT, waduk, 600+ pompa)
- Offline KB entry `jalan` + `_matchOffline` routing for street/road queries
- Klarifikasi: Jakarta = 5 kota administrasi + Kep. Seribu (bukan kabupaten biasa)
