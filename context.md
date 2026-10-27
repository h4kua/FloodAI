# deFlood.ai — Project Context

> Last updated: 2026-10-24 (branch `design/simplify-ui`). Update this file whenever architecture,
> known issues, or deployment state changes. Every fact here was checked against the code on that date.

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI + uvicorn, port 8080 |
| Frontend | React 18 + Vite 5 + React-Leaflet 4, port 3000 (dev); basemap Esri Gray Canvas (keyless) |
| Database | Supabase / PostgreSQL (`supabase` client + psycopg2) |
| ML | XGBoost + scikit-learn 1.8.0 — realtime-native bundle (`models/realtime_native_bundle/`, 17 features). Retrained 2026-10-23 with a leak-free frequency feature. Test AUC 0.904 / recall 0.893 / ECE 0.062 are optimistic: bootstrap-proxy data, random split, no field evaluation yet (see *Model & evaluation*). |
| LLM | Groq `qwen/qwen3.8-27b` (`DEFAULT_GROQ_MODEL` in `config/llm_config.py`, override with `GROQ_MODEL`; `llama-3.3-70b-versatile` was withdrawn) for the chatbot, explanations and 3-agent crew. Not in the decision path. |
| Deploy | Fly.io backend (`fly.toml`, app `floodai-8eclra`, region `ams`) · Vercel frontend (`vercel.json`, SPA rewrite to `index.html`) |

---

## Run

```bash
# Backend (refreshes the snapshot on startup, then every 15 min)
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload

# Frontend (Vite proxies /predict, /api, /healthz, /shelters → :8080)
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
| `api/routes/chat.py` | `POST /api/chat` — Groq chatbot (`max_tokens=800`, `timeout=28s`), per-IP rate limit |
| `api/ip_rate_limit.py` | Per-IP limits; behind Fly.io the client IP comes from `Fly-Client-IP` (trusted only when `FLY_APP_NAME` is set) |
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
| `frontend/src/styles.css` | Single stylesheet, light (default) + dark theme |
| `frontend/src/components/BaseTiles.jsx` | Shared basemap (Esri Gray Canvas base + labels, light/dark) |

---

## Endpoints

| Endpoint | Auth | Notes |
|---|---|---|
| `GET /predict/realtime-native` | — | Main endpoint used by the UI |
| `GET /predict/realtime` | — | **Retired 2026-10-24**: `410 Gone` + `Link` to `/predict/realtime-native` (legacy Jakarta model, sunset was 2026-06-30) |
| `POST /predict/agentic` | X-Api-Key | Full 5-stage pipeline |
| `POST /predict/agentic/explain` | X-Api-Key | Pipeline + LLM explanation |
| `GET /predict/crew-realtime` | — | 3-agent analysis on the live snapshot, cached per snapshot |
| `POST /predict/crew-analysis` | X-Api-Key | 3-agent analysis on a supplied snapshot |
| `POST /api/chat`, `GET /api/chat/health` | IP rate limit (chat) | Chatbot; `FLOOD_CHAT_RATE_LIMIT` per IP per minute (default 10), own buckets; on 429 the frontend uses its offline KB |
| `POST /shelters/checkin` | IP rate limit | Used by Evakuasi ("Saya sudah tiba") |
| `/reports`, `/sos`, `/sos/recent`, `/family/*` | IP rate limit | **Off by default** (404): registered only when `COMMUNITY_API_ENABLED=true`. No UI uses them; route code stays tested on a bare app |
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
  "wilayah_jakarta": "Jakarta Selatan", // canonical (null = upstream), realtime_native/wilayah.py
  "lokasi": "Banjir Kanal Barat",       // river / channel
  "tinggi_air": 503.6,                   // cm (DSDA sends mm; poskobanjir/services/parser.py converts)
  "siaga1": 600.0, "siaga2": 550.0, "siaga3": 500.0,
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
├── page header            — title + "Perbarui" (icon only on phones)
├── StaleDataBanner        — shown when data is > 30 min old
├── DecisionHero           — solid status block (Aman/Waspada/Siaga/Bahaya), plain-language text,
│                            trend + rain pills, "Pos pantau air" gauge (one segment per post,
│                            worst first, counts per level); greyed out with date when data ≥ 3 h old
├── WilayahStatus          — 5 wilayah, status = worst post in each (status-coloured stripe)
├── home-main (2 columns from 769 px)
│   ├── FloodMap           — Leaflet, DSDADKI posts (outlined markers); BNPB flood-prone points off by default
│   └── ActionCard         — up to 3 plain-language actions + CTA buttons (deriveActions)
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
| `groupStationsByWilayah()`, `stationWilayah()` | Groups posts by the backend's `wilayah_jakarta` (corrections live in `realtime_native/wilayah.py`) |
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

Civic "public information board" style; light theme is the default.
- Fonts: Public Sans (text), Barlow Condensed (headings, status word, big numbers).
- Light: `--bg #f5f3ee` (paper), `--panel #ffffff`, thin `--line` rules. Dark: flat `--bg #111214`, `--panel #18191c`.
- Chrome: navy top bar/footer (`--chrome #12233f`) with a water-blue accent (`--chrome-accent`); accent `--cyan` is civic blue `#1d4ed8`.
- Status colours are reserved for status: Aman/Normal green, Waspada amber, Siaga/Siaga 2 orange, Bahaya/Siaga 1 red;
  each has text (`--safe`, `--wsp`, `--s2`, `--s1`), `-soft`, `-border` and `-solid` (+ `-ink`) variants. Text pairs ≥ 4.5:1.
- Post vocabulary everywhere (gauge, list, map legend): Siaga 1 / Siaga 2 / Waspada / Normal; DSDA "Siaga 3" is shown as Waspada.
- No gradients, glows or blur; radius 4–10 px; sentence-case labels.

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
| AUC 0.904 [0.866–0.940], PR-AUC 0.528, recall 0.893, precision 0.263, Brier 0.074, ECE 0.062, threshold 0.103 | `artifacts/reports/model_evaluation.md` (`scripts/evaluate_model.py`, 95 % bootstrap CIs) | Current bundle (retrained 2026-10-23) | Random stratified split (586 test rows from 2020–2024, 56 positives), leak-free frequency feature, `bootstrap_proxy` data; optimistic |
| AUC 0.901, recall 0.839, threshold 0.036 | git history (d06dc0c and earlier) | Previous bundle (2026-07-02) | Same split, leaky frequency feature |
| ECE 0.1962 | `artifacts/configurations/calibration_cache.json` | Older model (Apr–May 2026 predictions) | Labels derived from the model's own ranking; still read at runtime, penalty off |
| ECE 0.3784 | `artifacts/reports/scenario_validation.json` | Older model | n = 7 hand-made scenarios |
| AUC 0.9452 | `artifacts/reports/model_training_report_jakarta.txt` | Legacy Jakarta model (`/predict/realtime`) | Random 80:20 split, train AUC 1.0 |

- **Split:** random stratified 68/12/20 — the chronological validation slice (May 2023–Jan 2024)
  has 0 positives, so training falls back to random; the report records this as
  `random_stratified_68_12_20 (fallback: …)`. `year_split=(val_year, test_year)` gives a by-year split.
- **Leakage fixed (2026-10-23):** `kecamatan_historical_flood_freq` is computed per row from BPBD
  events in earlier years only (`events_by_year` in `data/bundled/kelurahan_flood_history.json`);
  inference uses years before the snapshot's year, so training and serving match.
- **Honest estimate (by-year split train 2020–2022 / val 2023 / test 2024, 22 positives):**
  AUC 0.812 [0.741–0.869], PR-AUC 0.104 (no-skill 0.037), recall 0.864 / precision 0.124 at the
  threshold picked on 2023, ECE 0.192 (`artifacts/reports/model_evaluation.md`). Earlier sandbox runs:
  without the frequency feature AUC 0.84, leaky feature AUC 0.89. Very few 2023–2024 positives
  (11 and 22), so these are rough.
- **Evaluation fixes (2026-10-24):** ECE now uses equal-width bins consistently (the old function
  gave 0.018 for this bundle); calibration method chosen on the validation fold; the threshold rule
  no longer returns 1.0 / recall 0 when no threshold reaches precision 0.30 (falls back to best F2);
  the served bundle ships one booster per calibration fold, so serving equals training.
- **Proxy features in the training data:** the 2,928 kecamatan-month rows (2020–2024) are `bootstrap_proxy`:
  water-level features are derived from rainfall (`max_rainfall / q95`), humidity from soil moisture, BMKG
  scores from rainfall, missing temperature filled with 28.5 °C (`build_bootstrap_training_dataset()`).
  Serving uses real DSDA/BMKG/OpenWeather values every 15 min, so training and serving distributions differ.
- **No observed row-level flood labels** for evaluation: `realtime_feature_history.csv` has no label
  column; `calibration_labeled.csv` labels are synthetic; `bpbd_flood_calendar.csv` is quarterly
  aggregates. Per-incident BPBD data (`data/raw/rekap_kejadian_2020_2025.csv`, git-ignored) has dates
  but does not overlap the realtime period (Apr–May 2026).

---

## Known issues

| Issue | Status | Impact |
|---|---|---|
| No valid field calibration | Active | See *Model & evaluation*; calibration penalty is off |
| Feature leakage in test metrics | Resolved 2026-10-23 | Bundle retrained with the leak-free feature; the random split still makes metrics optimistic |
| No observed flood labels for evaluation | Active | Model quality in the field is unknown |
| Wilayah override | Resolved 2026-10-23 | Single source in `realtime_native/wilayah.py`; stations carry `wilayah_jakarta` and the frontend groups by it |
| DSDADKI misfiles posts | Active | Hek Kramat Jati 1 and Kaliduri 1 are filed under Jakarta Utara at the source (corrected by the override) |
| Kecamatan table partly unverified | Active | `_STATION_KEC` entries other than the corrected Ancol/removed ones are unchecked |
| Posts without GPS | Active | e.g. Bendung Katulampa (`lat=null`): listed, not mapped |
| Unused public write APIs | Resolved 2026-10-24 | Off by default; `COMMUNITY_API_ENABLED=true` re-exposes them |
| Chatbot without rate limit | Resolved 2026-10-24 | `POST /api/chat` limited per IP; Fly client IP read from `Fly-Client-IP` |
| Legacy `/predict/realtime` | Resolved 2026-10-24 | Retired (410); `services/prediction_service.py` + legacy model files remain for `services/training_data_monitor.py` |
| CARTO basemap watermark | Resolved 2026-10-23 | CARTO now watermarks keyless tiles; switched to Esri Gray Canvas |
| Free third-party services | Active | Esri keyless tiles, OSRM demo server and Nominatim have usage policies; production traffic needs keys or own servers |
| No CI before 2026-10-24 | Resolved | `.github/workflows/ci.yml`: pytest + frontend build on PRs and pushes to `main` |
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
| `FLOOD_IP_RATE_LIMIT`, `FLOOD_CHAT_RATE_LIMIT` | Per-IP limits per minute: public endpoints (default 20), chatbot (default 10) |
| `COMMUNITY_API_ENABLED` | `true` registers `/reports`, `/sos`, `/family/*` (default `false`) |
| `FLY_APP_NAME` | Set by Fly.io; enables trusting `Fly-Client-IP` for rate limiting |
| `GROQ_API_KEY`, `GROQ_MODEL`, `LLM_PROVIDER` | LLM provider (Groq default) |
| `ANTHROPIC_API_KEY` (+ `ANTHROPIC_*`) | Optional Claude provider |
| `OPENWEATHER_API_KEY` | Weather in the snapshot builder |
| `SUPABASE_URL`, `SUPABASE_KEY` | Supabase client |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PERSISTENCE_ENABLED` | Direct/pooled Postgres |
| `SNAPSHOT_REFRESH_INTERVAL_MINUTES` | Scheduler interval (default 15, valid 1–60) |
| `SNAPSHOT_SCHEDULER_ENABLED` | `false` skips the background refresh (set by `tests/conftest.py`); default `true` |
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
- Bundle retrained with a leak-free `kecamatan_historical_flood_freq` (2026-10-23).
- Frontend redesign (2026-10-23/24): civic public-information style (see *Design system*), Esri basemap,
  post gauge in the status card, one status vocabulary, GlanceChips removed, two-column map layout.
- Ops (2026-10-24): chatbot rate limit, community write endpoints off by default, `/predict/realtime`
  retired, CI workflow, README rewritten.

Full history: `git log`.
