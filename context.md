# deFlood.ai — Project Context

> Last updated: 2026-10-22 (branch `design/simplify-ui`). Update this file whenever architecture,
> known issues, or deployment state changes. Every fact here was checked against the code on that date.

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI + uvicorn, port 8080 |
| Frontend | React 18 + Vite 5 + React-Leaflet 4, port 3000 (dev) |
| Database | Supabase / PostgreSQL (`supabase` client + psycopg2) |
| ML | XGBoost + scikit-learn 1.8.0 — realtime-native bundle (`models/realtime_native_bundle/`, 17 features). Test-split AUC 0.901 / recall 0.839 / ECE 0.014 are optimistic: bootstrap-proxy data with feature leakage, no field evaluation yet (see *Model & evaluation*). |
| LLM | Groq `llama-3.3-70b-versatile` (chatbot, explanations, 3-agent crew). Not in the decision path. |
| Deploy | Fly.io backend (`fly.toml`, app `floodai-8eclra`, region `ams`) · Vercel frontend (`vercel.json`, SPA rewrite to `index.html`) |

---

## Run

```bash
# Backend (refreshes the snapshot on startup, then every 15 min)
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload

# Frontend (Vite proxies /predict, /api, /healthz, /family, /sos, /shelters → :8080)
cd frontend && npm run dev

# Manual snapshot refresh (same builder the scheduler runs)
cd poskobanjir && python main.py

# Water-gate levels + AWLR thresholds from Jakarta Satu ArcGIS
python scripts/run_tma_scraper.py
```

---

## Data flow

1. **Snapshot builder** — `poskobanjir/main.py` fetches DSDADKI water levels
   (`datatmalaststatus.json` + `xmldata.xml`), BMKG `cuaca.json` + nowcast alerts, and OpenWeather
   (Jakarta centre + 5 wilayah, `lang=id`). Writes `poskobanjir/data/raw/*.json` and
   `poskobanjir/data/clean/realtime_snapshot.json`.
2. **Scheduler** — `api/main.py` (APScheduler) runs the builder via `services/snapshot_refresh.py`
   (subprocess) on startup and every `SNAPSHOT_REFRESH_INTERVAL_MINUTES` (default 15), and saves to
   Supabase. On Fly.io the GitHub Action `.github/workflows/refresh-snapshot.yml` also pings
   `POST /internal/refresh-snapshot` every 15 min.
3. **Inference** — `realtime_native/inference.py` builds features, runs the bundle, writes
   `artifacts/reports/latest_realtime_native_prediction.json`, and serves `GET /predict/realtime-native`.
4. **Frontend** — `useFloodRisk.js` polls that endpoint every 5 min.

The files in steps 1 and 3 are runtime data and are git-ignored; a fresh clone recreates them on the
first backend start.

---

## Key paths

| Path | Purpose |
|---|---|
| `api/main.py` | FastAPI app, CORS, scheduler, core endpoints |
| `api/routes/chat.py` | `POST /api/chat` — Groq chatbot (`max_tokens=800`, `timeout=28s`) |
| `api/routes/crew_analysis.py` | 3-agent "Analisis mendalam"; rebuilds observed rain/water `features` from the pipeline result |
| `api/routes/safe_arrival.py` | `POST /shelters/checkin` — geofenced check-in, returns `family_notified` |
| `domain/decision.py` | Decision layers L0–L4 (source of truth) |
| `services/decision_engine.py` | Adapter around the decision layers; calibration penalty is off |
| `realtime_native/inference.py` | `GET /predict/realtime-native`, builds `wilayah_summary` |
| `realtime_native/feature_builder.py` | 17 features + `stations_summary` from the snapshot |
| `agents/llm_orchestrator.py` | LLM explanation + deterministic fallback text (built from observed features) |
| `poskobanjir/` | Self-contained snapshot builder (own import root; run with `cwd=poskobanjir`) |
| `frontend/src/pages/` | `Home.jsx` (Beranda), `Alert.jsx` (Evakuasi), `About.jsx` (Tentang), `SafeArrival.jsx` (overlay) |
| `frontend/src/components/dashboard/` | Home building blocks (see below) |
| `frontend/src/lib/dashboardHelpers.js` | Status text, data freshness, trend label, wilayah grouping |
| `frontend/src/lib/recommendations.js` | `deriveActions()` for the "Apa yang harus saya lakukan?" card |
| `frontend/src/lib/floodAgent.js` | Chatbot client: `/api/chat` + offline knowledge base |
| `frontend/src/lib/translations.js` | All UI text, ID + EN |
| `frontend/src/styles.css` | Single stylesheet, dark + light theme |

---

## Endpoints

| Endpoint | Auth | Notes |
|---|---|---|
| `GET /predict/realtime-native` | — | Main endpoint used by the UI |
| `GET /predict/realtime` | — | Legacy Jakarta model (`flood_model_jakarta.pkl`); not used by the UI |
| `POST /predict/agentic` | X-Api-Key | Full 5-stage pipeline |
| `POST /predict/agentic/explain` | X-Api-Key | Pipeline + LLM explanation |
| `GET /predict/crew-realtime` | — | 3-agent analysis on the live snapshot, cached per snapshot |
| `POST /predict/crew-analysis` | X-Api-Key | 3-agent analysis on a supplied snapshot |
| `POST /api/chat`, `GET /api/chat/health` | — | Chatbot |
| `POST /shelters/checkin` | IP rate limit | Used by Evakuasi ("Saya sudah tiba") |
| `/reports`, `/sos`, `/sos/recent`, `/family/*` | IP rate limit | Still registered; **no UI uses them** since the Laporan, SOS and Keluarga pages were removed |
| `GET /health`, `GET /healthz` | — | Liveness + scheduler + snapshot age |
| `GET /readyz` | — | Readiness (DB + thresholds) |
| `GET /metrics` | — | Prometheus |
| `GET /demo`, `GET /dashboard` | — | Server-rendered operator dashboard |
| `POST /internal/refresh-snapshot` | X-Internal-Secret | Disabled (503) when `INTERNAL_SECRET` is unset; rate-limited |

---

## `/predict/realtime-native` — fields the frontend reads

`useFloodRisk.js` maps the response to `riskData`:

| `riskData` | Response field |
|---|---|
| `level` | `risk_level`: SAFE→aman, PRE_ALERT→waspada, WARNING→siaga, DANGER→bahaya |
| `riskScore` | `probability × 100` |
| `interpretation` | `risk_interpretation` |
| `rainfall`, `humidity`, `temperature`, `monsoonSeason` | `features.*` |
| `waterLevelRatio`, `waterLevelDelta` | `features.water_level_ratio`, `features.water_level_delta` |
| `trendState` | `diagnostics.trend_state` (`risk_trend`, `anomaly_*`, `risk_delta_1h`) |
| `tmaStationsActive` | `diagnostics.water_level_records` |
| `isOutlier` | `ood_detection.is_outlier` |
| `stations` | `stations[]` (see below) |
| `wilayahSummary` | `wilayah_summary[]` — per-wilayah DSDADKI status counts + BMKG forecast slots |
| `openweather`, `openweatherWilayah` | `openweather_current`, `openweather_wilayah` |
| `bmkgForecast` | `bmkg_forecast` (DKI-wide fallback) |
| `recommendedActions` | `recommended_action` (only "kelurahan" lines are shown) |
| `snapshotFetchedAt` | `snapshot_fetched_at` |

### `stations[]`

```jsonc
{
  "nama": "P.A. Karet 1",
  "wilayah": "KOTA JAKARTA SELATAN",   // DSDADKI file_export, as sent
  "lokasi": "Banjir Kanal Barat",       // river / channel
  "tinggi_air": 5036.0,                  // cm
  "siaga1": 6000.0, "siaga2": 5500.0, "siaga3": 5000.0,
  "status_siaga": "Status : Siaga 3",
  "ratio": 0.839,                        // tinggi_air / siaga1
  "lat": -6.2234, "lon": 106.8015        // null when missing or outside Jakarta
}
```

Excluded from scoring (listed in `diagnostics.station_quality`): pump stations (`POMPA…`),
uncalibrated stations (placeholder thresholds), non-standard datum.

---

## Frontend

### Pages and navigation

Three destinations (`components/shell/navConfig.jsx`): **Beranda**, **Evakuasi**, **Tentang**.
`TopBar` (desktop) and `BottomNav` (mobile) share that config. `OnboardingTour` has 4 steps.

### Beranda (`pages/Home.jsx`)

```
Home
├── page header            — title + "Perbarui"
├── StaleDataBanner        — shown when data is > 30 min old
├── DecisionHero           — status word, plain-language text, trend pill; greyed out with date when data ≥ 3 h old
├── WilayahStatus          — 5 wilayah, status = worst post in each
├── ActionCard             — up to 3 actions + CTA buttons (deriveActions)
├── GlanceChips            — water level, rain, posts on alert, active posts
├── FloodMap               — Leaflet, DSDADKI posts + optional BNPB flood-prone points
├── CollapsibleSection "Lihat detail" (tabs)
│   ├── Analisis AI        — ModelOutputCard + CrewAnalysisPanel
│   ├── Ketinggian air     — StationPanel, grouped by wilayah
│   └── Cuaca              — WeatherCurrentCard + WilayahForecastGrid (or ForecastPanel)
└── ChatBot
```

### Helpers that shape what users read (`lib/dashboardHelpers.js`)

| Helper | What it does |
|---|---|
| `buildStatusDesc()` | Status sentence from live posts; never says "all normal" when posts are at Waspada |
| `STALE_STATUS_MIN` (180), `dataAgeMinutes()`, `formatDataTime()` | Stale-data handling; adds the date once data is old |
| `trendDisplay()` | Trend label whose tone follows the status (a rise under "Aman" stays neutral) |
| `groupStationsByWilayah()`, `stationWilayah()` | Groups posts by wilayah from DSDADKI names, with `WILAYAH_OVERRIDE` for misfiled posts |
| `stationKecamatan()` | Kecamatan label; entries contradicting coordinates were removed |

### Evakuasi (`pages/Alert.jsx`)

GPS "Cari tempat pengungsian terdekat" CTA, address search (Nominatim), route map, shelter card
(address, capacity, call, "Saya sudah tiba"), emergency contacts, evacuation steps, emergency-bag list.
Arrival is auto-detected by `useShelterGeofence`.

### Tentang (`pages/About.jsx`)

Plain intro, 3-step "Cara kerjanya", caveats, team. Model metrics, data sources, ML/AI notes and stack
live in a collapsed "Detail teknis" section, with the evaluation caveats stated next to the numbers.

### Chatbot (`lib/floodAgent.js`)

- `sendToFloodAgent()` posts to `/api/chat` with `SYSTEM_PROMPT` + live context; 28 s abort timeout.
- On failure: `_matchOffline()` → `OFFLINE_KB[lang]` keys `evakuasi, status, wilayah, tanda, shelter,
  kontak, durasi, dokumen, cuaca, pasca, prediksi, pompa, jalan, web, rtrw, landmark, jarak`;
  otherwise a generic offline message with emergency numbers.

### Design system (`styles.css`)

- Fonts: DM Sans (body), Space Grotesk (headings). No monospace labels.
- Dark: `--bg #0d1117`, `--panel #161b22`, `--panel-2 #1c2333`, `--panel-3 #21293b`.
- Light: `--bg #f4f2ee`, `--panel #faf9f7`, `--panel-2 #edeae4`, `--panel-3 #e3dfd8`.
- Status colours: `--safe`, `--wsp` (waspada), `--s2`, `--s1`, each with `-soft` / `-border` variants.
- Sentence-case labels, minimum ~12 px text, no 3D tilt effects.

---

## Decision hierarchy (`domain/decision.py`)

```
L0   PHYSICAL        invalid input → UNKNOWN/FAIL (non-bypassable)
L1   SIAGA           water_level_ratio ≥ 0.90 anywhere → DANGER
L1.5 MULTI           ≥ 2 of {rain ≥ 60, water ≥ 0.85, BMKG ≥ 0.80} → DANGER
L1.7 BMKG_FLOOR      BMKG-severe + (high rain OR OOD + stale TMA) → WARNING floor
L2   INTEGRITY       severe failures → escalate one level
L3   ML              calibrated probability vs adaptive thresholds
L3.1 PRECISION_GATE  post-ML: suppress marginal PRE_ALERT when the baseline disagrees
L1.8 HYDRO_FLOOR     post-ML: ratio ≥ 0.75 → WARNING, ≥ 0.60 → PRE_ALERT (one-way)
L1.9 OOD_FLOOR       post-ML: OOD score < −0.05 → PRE_ALERT, < −0.10 → WARNING (with confidence caps)
L4   TREND           sustained rise → WARNING → DANGER (one-way)
```

The LLM never changes the decision; it only writes explanations, with a deterministic fallback.

---

## Model & evaluation

| Figure | Source | Model | Caveat |
|---|---|---|---|
| AUC 0.901, recall 0.839, precision 0.263, Brier 0.072, ECE 0.014 | `models/realtime_native_bundle/training_stats.json` | Current bundle (created 2026-07-02) | Test split = 586 monthly rows, Jan–Dec 2024, `bootstrap_proxy` features; optimistic |
| ECE 0.1962 | `artifacts/configurations/calibration_cache.json` | Older model (Apr–May 2026 predictions) | Labels derived from the model's own ranking; still read at runtime, penalty off |
| ECE 0.3784 | `artifacts/reports/scenario_validation.json` | Older model | n = 7 hand-made scenarios |
| AUC 0.9452 | `artifacts/reports/model_training_report_jakarta.txt` | Legacy Jakarta model (`/predict/realtime`) | Random 80:20 split, train AUC 1.0 |

- **Leakage:** `kecamatan_historical_flood_freq` comes from `data/bundled/kelurahan_flood_history.json`
  (BPBD events 2020–2026, all years pooled), which includes the 2024 test period.
- **Split:** named `chronological_80_15_5`, actually 68/12/20 (train 1990 / val 352 / test 586).
- **No observed row-level flood labels** for evaluation: `realtime_feature_history.csv` has no label
  column; `calibration_labeled.csv` labels are synthetic; `bpbd_flood_calendar.csv` is quarterly
  aggregates. Per-incident BPBD data (`data/raw/rekap_kejadian_2020_2025.csv`, git-ignored) has dates
  but does not overlap the realtime period (Apr–May 2026).

---

## Known issues

| Issue | Status | Impact |
|---|---|---|
| No valid field calibration | Active | See *Model & evaluation*; calibration penalty is off |
| Feature leakage in test metrics | Active | Bundle test metrics are inflated |
| No observed flood labels for evaluation | Active | Model quality in the field is unknown |
| Wilayah override duplicated | Active | `WILAYAH_OVERRIDE` exists in both `dashboardHelpers.js` and `realtime_native/inference.py`; change both together |
| DSDADKI misfiles posts | Active | Hek Kramat Jati 1 and Kaliduri 1 are filed under Jakarta Utara at the source (corrected by the override) |
| Kecamatan table partly unverified | Active | `_STATION_KEC` entries other than the corrected Ancol/removed ones are unchecked |
| Posts without GPS | Active | e.g. Bendung Katulampa (`lat=null`): listed, not mapped |
| Unused public write APIs | Active | `/reports`, `/sos`, `/family/*` have no UI; remove or re-expose deliberately |
| Emergency numbers | Resolved 2026-10-22 | Ambulance is 119 (or 112) everywhere, per Dinkes DKI; 118 is the older number |
| `min_machines_running` | Resolved 2026-10-22 | `fly.toml` keeps 1 machine on (2477fcb); the refresh workflow is a backup and its comment now says so |
| BNPB district mapping gap | Active | Some kecamatan not mapped to kabkot; InaRISK falls back to bundled JSON |
| Legacy TMA Selenium scraper | Disabled by design | No `TMA_PROXY_URL`; degrades to STALE |
| BMKG slots every ~3–6 h | By design | Forecast title shows the real span (e.g. "2 hari ke depan") |

---

## Environment variables

Names only — values live in `.env` (never committed; `.env.example` holds placeholders).

| Variable | Used for |
|---|---|
| `FLOOD_API_KEYS`, `FLOOD_API_RATE_LIMIT` | X-Api-Key auth + rate limit |
| `GROQ_API_KEY`, `GROQ_MODEL`, `LLM_PROVIDER` | LLM provider (Groq default) |
| `ANTHROPIC_API_KEY` (+ `ANTHROPIC_*`) | Optional Claude provider |
| `OPENWEATHER_API_KEY` | Weather in the snapshot builder |
| `SUPABASE_URL`, `SUPABASE_KEY` | Supabase client |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PERSISTENCE_ENABLED` | Direct/pooled Postgres |
| `SNAPSHOT_REFRESH_INTERVAL_MINUTES` | Scheduler interval (default 15, valid 1–60) |
| `INTERNAL_SECRET` | `/internal/refresh-snapshot` |
| `CREW_TIMEOUT_S` | 3-agent crew budget (default 45 s) |
| `VITE_API_BASE_URL` (frontend) | Empty = Vite proxy (dev); backend URL in production |

---

## Recent changes (branch `design/simplify-ui`, 2026-10)

- UI simplified for residents: readable sentence-case text, no 3D tilt, one collapsed "Lihat detail"
  section with tabs, plain-language status and evacuation copy, shorter tour.
- Removed the Laporan (community reports), SOS and Keluarga pages from the frontend.
- Honest status: stale data greys out the status and shows the date; trend/advice follow the status;
  AI fallback text uses observed values; safe-arrival only claims "family notified" when true.
- Status per wilayah on Beranda; water-level list grouped by wilayah; backend `wilayah_summary` now
  matches DSDADKI's "KOTA JAKARTA …" names.
- Crew endpoints pass observed rain/water features to the agents.
- OpenWeather descriptions in Indonesian; forecast title follows the real slot span.
- Runtime data (`poskobanjir/data/*`, latest prediction artifact) no longer tracked in git.
- Metrics and calibration stated with their real sources and caveats (About page, CLAUDE.md, this file).

Full history: `git log`.
