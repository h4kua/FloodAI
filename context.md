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
| ML | XGBoost + scikit-learn 1.8.0 — realtime-native bundle (`models/realtime_native_bundle/`, 17 features). Retrained 2026-10-28 (leak-free frequency feature, BPBD events counted once per RW-date). Test AUC 0.899 / recall 0.875 / ECE 0.062 are optimistic: bootstrap-proxy data, random split, no field evaluation yet (see *Model & evaluation*). |
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
| `api/routes/chat.py` | `POST /api/chat` — Groq chatbot: server-side prompt from `api/chat_knowledge.txt`, model fallback, runs off the event loop, per-IP rate limit |
| `api/chat_knowledge.txt` | Chatbot knowledge: core rules (always sent) + topic sections sent only when the question touches them |
| `api/routes/community_reports.py` | `GET/POST /reports`, `POST /reports/photo` (Laporan page) |
| `api/ip_rate_limit.py` | Per-IP limits; behind Fly.io the client IP comes from `Fly-Client-IP` (trusted only when `FLY_APP_NAME` is set) |
| `api/routes/crew_analysis.py` | 3-agent "Analisis mendalam"; rebuilds observed rain/water `features` from the pipeline result |
| `api/routes/safe_arrival.py` | `GET /shelters/nearby` (nearest shelter candidates); `POST /shelters/checkin` — geofenced check-in, returns `family_notified` |
| `domain/decision.py` | Decision layers L0–L4 (source of truth) |
| `services/decision_engine.py` | Adapter around the decision layers; calibration penalty is off |
| `realtime_native/inference.py` | `GET /predict/realtime-native`, builds `wilayah_summary` |
| `realtime_native/feature_builder.py` | 17 features + `stations_summary` from the snapshot |
| `agents/llm_orchestrator.py` | LLM explanation + deterministic fallback text (built from observed features) |
| `poskobanjir/` | Self-contained snapshot builder (own import root; run with `cwd=poskobanjir`) |
| `frontend/src/pages/` | `Home.jsx` (Beranda), `Alert.jsx` (Evakuasi), `Reports.jsx` (Laporan), `About.jsx` (Tentang) |
| `frontend/src/components/dashboard/` | Home building blocks (see below) |
| `frontend/src/lib/dashboardHelpers.js` | Status text, data freshness, trend label, wilayah grouping, post level from the DSDA band (`postRiskLevel`) |
| `frontend/src/lib/floodRoads.js` | Flood-aware routing: active BPBD points, route scoring, Google Maps link |
| `frontend/src/lib/api.js` | One backend base (`VITE_API_BASE_URL`, trailing dots/slashes dropped) |
| `frontend/src/lib/floodAgent.js` | Chatbot client: `/api/chat` (no system prompt) + offline knowledge base; 429 = busy |
| `frontend/src/lib/translations.js` | All UI text, ID + EN |
| `frontend/src/styles.css` | Single stylesheet, light (default) + dark theme |
| `frontend/src/components/BaseTiles.jsx` | Shared basemap: Esri Gray Canvas (home map) or World Street Map (`variant="street"`, evacuation map) |

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
| `POST /api/chat`, `GET /api/chat/health` | IP rate limit (chat) | Chatbot; `FLOOD_CHAT_RATE_LIMIT` per IP per minute (default 10). Groq free tier = 8k tokens/min per model: falls back to `openai/gpt-oss-20b`, waits out a retry-after ≤ 3 s once, then 429 `ai_busy` (frontend says "busy", keeps the online status) |
| `GET /shelters/nearby?lat&lon&limit` | IP rate limit | ≤ 20 nearest shelter candidates in Jakarta (422 outside the city) |
| `POST /shelters/checkin` | IP rate limit | Kept in the API; the interface no longer uses it |
| `GET /reports`, `POST /reports` | IP rate limit | Laporan page: last 6 h, unverified, never changes the status; on unless `COMMUNITY_REPORTS_ENABLED=false` |
| `POST /reports/photo` | IP rate limit | ≤ 8 MB / 40 MP in, re-encoded JPEG ≤ 1280 px without metadata, Supabase bucket `report-photos` (migration 110) |
| `POST /reports/{id}/vote`, `GET`/`POST /reports/{id}/comments`, `POST /reports/{id}/flag` | IP rate limit (POST) | Reactions (migration 111): one like/dislike per device (`value` 1/-1, 0 takes it back), comments ≤ 300 chars, flags (spam/wrong/offensive/private); 3 flags hide a report. `GET /reports?device_id=` adds `likes`, `dislikes`, `comment_count`, `my_vote` and never returns device IDs. 503 `reactions_unavailable` until migration 111 runs |
| `/sos`, `/sos/recent`, `/family/*` | IP rate limit | **Off by default** (404): registered only when `COMMUNITY_API_ENABLED=true` |
| `GET /health`, `GET /healthz` | — | Liveness + scheduler + snapshot age |
| `GET /readyz` | — | Readiness: Supabase `realtime_snapshot_store` answers (+ Postgres pool when `DB_PERSISTENCE_ENABLED=true`) + thresholds |
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

Four destinations (`components/shell/navConfig.jsx`): **Beranda**, **Evakuasi**, **Laporan**, **Tentang**.
`TopBar` (desktop, pinned while scrolling) and `BottomNav` (≤ 768 px, one column per item) share that
config. The top bar holds the guide button ("?"), ID/EN and light/dark. `ErrorBoundary` wraps each page.
`OnboardingTour` has 11 steps (status, areas, map, details, each page, settings, chatbot); its card is
measured and kept between the top bar and the bottom nav, so its buttons are always on screen. Key
`deflood_tour_v8_done`.

### Beranda (`pages/Home.jsx`)

```
Home
├── page header            — title + refresh
├── StaleDataBanner        — shown when data is > 30 min old
├── DecisionHero           — status block (Aman/Waspada/Siaga/Bahaya/Tidak diketahui), plain-language text,
│                            trend + rain pills, Siaga line, post gauge (one segment per post, worst first);
│                            greyed out with date when data ≥ 3 h old
├── WilayahStatus          — 5 wilayah, status = worst post in each
├── FloodMap               — full width; shared post markers + active flood-area circles (mapLayers.jsx);
│                            legend floats and folds on desktop; under the map, always open, at ≤ 640 px
├── CollapsibleSection "Lihat detail" (tabs)
│   ├── Analisis AI        — ModelOutputCard (`risk_interpretation` / `risk_interpretation_en` by language)
│   │                        + CrewAnalysisPanel (3-agent output is Indonesian only)
│   ├── Ketinggian air     — StationPanel, grouped by wilayah
│   └── Cuaca              — WeatherCurrentCard + WilayahForecastGrid (or ForecastPanel)
└── ChatBot (lazy)
```

Every post's level comes from the band DSDA reports (`status_siaga`: Siaga 1 → Siaga 1, Siaga 2 →
Siaga 2, Siaga 3 → Waspada, Siaga 4/Normal → Normal), the same band the decision engine floors on;
the ratio to Siaga 1 is only the fallback. Gauge, Siaga line, wilayah cells, post list and map markers
all use `postRiskLevel()` / `postClass()`.

### Helpers that shape what users read (`lib/dashboardHelpers.js`)

| Helper | What it does |
|---|---|
| `buildStatusDesc()` | Status sentence from live posts; never says "all normal" when posts are at Waspada |
| `postRiskLevel()`, `postClass()`, `byPostSeverity()` | A post's level from its DSDA band (ratio fallback); worst-first ordering |
| `STALE_STATUS_MIN` (180), `dataAgeMinutes()`, `formatDataTime()` | Stale-data handling; adds the date once data is old |
| `trendDisplay()` | Trend label whose tone follows the status (a rise under "Aman" stays neutral) |
| `groupStationsByWilayah()`, `stationWilayah()` | Groups posts by the backend's `wilayah_jakarta`; each group carries its `worst` post |
| `stationKecamatan()` | Kecamatan label; entries contradicting coordinates were removed |

### Evakuasi (`pages/Alert.jsx`)

"Cari tempat pengungsian terdekat" CTA, then two rows: **Dari** (address with Nominatim suggestions,
GPS, or a tap on the map) and **Tujuan** (home by default once saved in localStorage, one of ~20
nearby shelter candidates from `GET /shelters/nearby` with type and distance, or any address). The
candidates come from `data/bundled/jakarta_shelters.json` (12,130 OSM/HOT InAWARE places: schools,
places of worship, RW/kelurahan offices; hospitals, clinics and same-name duplicates within 150 m
dropped). `rankSheltersByFlood` puts candidates within 500 m of an active flood-prone point last, and
the three nearest large venues (`DESTINATIONS`, no phone numbers) close the list and serve as the
offline fallback. The evacuation map uses Esri World Street Map up to zoom 19 (dark mode inverts it
with `.tiles-dark`); the home map keeps Gray Canvas. `EvacuationMap` asks OSRM for alternatives, colours each stretch
green/red by whether it passes within 500 m of an active BPBD flood-prone point (its river's post at
Siaga, or rain ≥ 20 mm/h; plus post-centred areas for Siaga posts without BPBD points), picks the
route with the least red, and shows a one-line summary with "Buka di Google Maps" (≤ 3 waypoints; no
origin for a GPS start). The step panel sits right of the zoom buttons. A typed address clears a
refused-GPS message.

### Laporan (`pages/Reports.jsx`)

List of the last 6 h (all / flooding only), each labelled unverified, with optional photo; a form with
severity, text (≤ 500), name, location and a photo shrunk in the browser before upload. Each card
(`components/ReportCard.jsx`) has 👍/👎 with counts (one vote per device ID from `lib/device.js`,
optimistic, rolled back on error), comments loaded on open, and a ⋯ menu: share (Web Share API or copy),
copy link, the place in Google Maps, and report (four reasons; hidden at once for that device). A link
`/?report=<id>` opens Laporan on that report (no guide on that visit).

### Tentang (`pages/About.jsx`)

Plain intro, 4-step "Cara kerjanya" (collect, estimate, tell, help you act), caveats (incl. reports),
team (project lead + three members; mentors removed 2026-10-27). A collapsed "Detail teknis" holds model metrics with their caveats and the 2026-10-27 experiment,
data sources (DSDA 38 points = 28 posts + 10 pump houses, BMKG, OpenWeather, BPBD, OSM/OSRM, reports),
model & AI (L0–L4 engine, Groq Qwen3) and the stack.

### Chatbot (`components/ChatBot.jsx`, `lib/floodAgent.js`, `api/routes/chat.py`)

- The client posts the message, history and live context to `/api/chat`; 28 s abort. It no longer sends
  a system prompt (it was 18 KB, cut to 12 KB by the server, ~5k tokens a question).
- The server builds the prompt: short guardrails, the core sections of `api/chat_knowledge.txt`, the
  topic sections the question touches (≤ 2,200 chars), compact live context (≤ 1,800 chars, status names
  in the app's words), the last 4 messages (≤ 400 chars each): ~1,800 tokens a question.
- Answers render bold text and lists in the bubble (no raw markdown, no HTML from the model).
- 429 from the API → "AI sedang sibuk" (offline KB answer if one matches), status stays online. Other
  failures → `_matchOffline()` → `OFFLINE_KB[lang]`, else a generic message with emergency numbers.

### Design system (`styles.css`)

v4 "Air tenang" (2026-10-27): cool off-white page `--bg #f3f5f8`, white cards with a hairline and a soft
shadow, radii 8–22 px plus pills, one typeface (Plus Jakarta Sans), frosted top bar and bottom nav
(`--chrome-glass`). Dark theme redefines the same tokens.
- Status colours are reserved for status: Aman/Normal green, Waspada amber, Siaga/Siaga 2 orange, Bahaya/Siaga 1 red;
  each has text (`--safe`, `--wsp`, `--s2`, `--s1`), `-soft`, `-border` and `-solid` (+ `-ink`) variants. Text pairs ≥ 4.5:1.
- Post vocabulary everywhere (gauge, list, map legend): Siaga 1 / Siaga 2 / Waspada / Normal; DSDA "Siaga 3" is shown as Waspada.
- `html`/`body` use `overflow-x: clip` (not `hidden`, which broke the sticky top bar); `.main *` has a
  scroll margin so anchors and guide steps clear the bars. Checked at 360–1920 px without sideways scroll.

---

## Decision hierarchy (`domain/decision.py`)

```
L0   PHYSICAL        invalid input → UNKNOWN/FAIL (non-bypassable)
L1   SIAGA           highest post at its own DSDA Siaga 1 band → DANGER (ratio ≥ 0.90 without per-post bands)
L1.5 MULTI           ≥ 2 of {rain ≥ 60, water ≥ 0.85, BMKG ≥ 0.80} → DANGER
L1.7 BMKG_FLOOR      BMKG-severe + (high rain OR OOD + stale TMA) → WARNING floor
L2   INTEGRITY       severe failures → escalate one level
L3   ML              calibrated probability vs adaptive thresholds
L3.1 PRECISION_GATE  post-ML: suppress marginal PRE_ALERT when the baseline disagrees
L1.8 HYDRO_FLOOR     post-ML: Siaga 2 band → WARNING, Siaga 3 band → PRE_ALERT (ratio 0.75/0.60 fallback; one-way)
L1.9 OOD_FLOOR       post-ML: OOD score < −0.05 → PRE_ALERT, < −0.10 → WARNING (with confidence caps)
L4   TREND           sustained rise → WARNING → DANGER (one-way)
```

The LLM never changes the decision; it only writes explanations, with a deterministic fallback.

---

## Model & evaluation

| Figure | Source | Model | Caveat |
|---|---|---|---|
| AUC 0.899 [0.858–0.938], PR-AUC 0.525, recall 0.875, precision 0.282, Brier 0.074, ECE 0.062, threshold 0.126 | `artifacts/reports/model_evaluation.md` (`scripts/evaluate_model.py`, 95 % bootstrap CIs) | Current bundle (retrained 2026-10-28) | Random stratified split (586 test rows from 2020–2024, 56 positives), leak-free frequency feature from deduplicated BPBD events, `bootstrap_proxy` data; optimistic |
| AUC 0.904, recall 0.893, precision 0.263, threshold 0.103 | git history (5919525 and earlier) | Bundle of 2026-10-23 | Same split; frequency feature counted each RT row as an event (7,301 instead of 4,667) |
| AUC 0.901, recall 0.839, threshold 0.036 | git history (d06dc0c and earlier) | Bundle of 2026-07-02 | Same split, leaky frequency feature |
| ECE 0.1962 | `artifacts/configurations/calibration_cache.json` | Older model (Apr–May 2026 predictions) | Labels derived from the model's own ranking; still read at runtime, penalty off |
| ECE 0.3784 | `artifacts/reports/scenario_validation.json` | Older model | n = 7 hand-made scenarios |
| AUC 0.9452 | `artifacts/reports/model_training_report_jakarta.txt` | Legacy Jakarta model (`/predict/realtime`) | Random 80:20 split, train AUC 1.0 |

- **Split:** random stratified 68/12/20 — the chronological validation slice (May 2023–Jan 2024)
  has 0 positives, so training falls back to random; the report records this as
  `random_stratified_68_12_20 (fallback: …)`. `year_split=(val_year, test_year)` gives a by-year split.
- **Leakage fixed (2026-10-23):** `kecamatan_historical_flood_freq` is computed per row from BPBD
  events in earlier years only (`events_by_year` in `data/bundled/kelurahan_flood_history.json`);
  inference uses years before the snapshot's year, so training and serving match.
- **Event counts fixed (2026-10-28):** the BPBD workbooks list one row per RT, but
  `rekap_kejadian_2020_2025.csv` keeps only the RW, so 2,634 rows were identical copies. The history
  builder now counts each RW-date once: 4,667 events 2020–Mar 2026 (was 7,301). The bundle was
  retrained on the corrected feature (serving the old bundle with it raised ECE 0.062 → 0.074).
- **Flood records available:** BPBD per-kelurahan daily events 2013–2020 (`data/raw/combined.csv` →
  `data/processed/events_clean.csv`, 5,889 rows), per-RW records 2020–2025 and quarterly per-kelurahan
  records to Mar 2026 (Q4 2025 missing). Training uses 2020–2024 only because the bootstrap features
  (`cleaned_flood_data_jakarta.csv`) exist only for those years.
- **Precision experiments (2026-10-28, `artifacts/reports/precision_experiments.md`,
  `daily_flood_experiment.md`):**
  - The dataset's `banjir` label marks 282 kecamatan-months; BPBD records show 895 (267/147/213/113/155,
    2020–2024), and the label covers only 276 of them. The "floods shrink over time" pattern is a label
    artifact.
  - Scored against BPBD records, the by-year model's 2024 alarms are right 53 % of the time (recall 51 %),
    not 13 %: about half the "false alarms" are recorded floods.
  - Retrained on BPBD labels, the chronological split works (113 validation positives) and by year gives
    ROC-AUC 0.760 [0.715–0.800], PR-AUC 0.501 (no-skill 0.264); at the best-F1 threshold on 2023,
    recall 0.73 / precision 0.48 on 2024. Ranking of BPBD floods is no better than the current model's
    (PR-AUC 0.555 vs 0.501), so the features, not the label, cap it.
  - Stricter Danger threshold for the served model (precision ≥ 0.50 on validation → 0.425): random-split
    test recall 0.66 / precision 0.44 instead of 0.875 / 0.282. On dataset labels by year the choice is
    unstable (11 validation positives).
  - Daily city-level flood days from BPBD dates + ERA5 rainfall (Open-Meteo): ROC-AUC 0.57–0.78, no better
    than the 3-day rain sum alone; rainfall alone cannot separate flood days. Water-level history is needed.
  - BPBD-label candidate bundle (`scripts/train_bpbd_candidate.py` → `models/candidates/realtime_native_bpbd_labels/`,
    `artifacts/reports/bpbd_candidate.md`): chronological test ROC-AUC 0.793, PR-AUC 0.563 (no-skill 0.263). Its
    validation thresholds (Waspada 0.186 / Siaga 0.204 / Bahaya 0.247, isotonic steps) put 57 % of 2024
    kecamatan-months at Bahaya, of which BPBD recorded a flood in 40 %. At equal alarm volume it is not more precise
    than the served model, and its label ("any RW flooded this month") does not match a live "flood now" status.
    Not promoted.
  - Nothing was promoted; the served bundle is unchanged.
- **Honest estimate (by-year split train 2020–2022 / val 2023 / test 2024, 22 positives):**
  AUC 0.826 [0.745–0.889], PR-AUC 0.124 (no-skill 0.037), recall 0.864 / precision 0.128 at the
  threshold picked on 2023, ECE 0.169 (`artifacts/reports/model_evaluation.md`; before the event-count
  fix: AUC 0.812, PR-AUC 0.104, ECE 0.192). Earlier sandbox runs:
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
| Fly stops/suspends the machines | Fix in `fly.toml` (2026-10-27) | `auto_stop_machines = 'off'`: with `'stop'` both machines were stopped or suspended despite `min_machines_running = 1`, halting the 15-min scheduler; live since 2026-10-27, one machine. The GitHub refresh workflow (needs `REFRESH_URL`, `INTERNAL_SECRET`) is the backup |
| Backend far from users | Resolved 2026-10-28 | Was Fly region `ams` (`/predict/realtime-native` ~1.0 s median, max 10 s from Singapore); moved to `sin`: 573 ms median, max 0.95 s; `/healthz` 324 ms; status + map ~0.5–0.8 s on a repeat visit |
| Groq per-minute quota | Mitigated 2026-10-27 | Free tier 8k tokens/min per model; prompt cut to ~1.8k tokens, fallback model, "busy" instead of offline. Heavy use still needs a paid tier |
| Home "Siaga 2" count from ratios | Resolved 2026-10-27 | Gauge, Siaga line, wilayah and map now use each post's DSDA band, like the engine |
| Model improvement | Tried 2026-10-27 | 609 variants by year (test 2024): none better at ~86 % recall; candidate (13 features, Platt on 2023) AUC 0.796 vs 0.826 after the event-count fix (was 0.733 vs 0.812) → served bundle kept (`artifacts/reports/candidate_comparison.md`) |
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
| `COMMUNITY_REPORTS_ENABLED` | `false` unregisters `/reports` (default on) |
| `COMMUNITY_API_ENABLED` | `true` registers `/sos`, `/family/*` (default `false`) |
| `FLY_APP_NAME` | Set by Fly.io; enables trusting `Fly-Client-IP` for rate limiting |
| `GROQ_API_KEY`, `GROQ_MODEL`, `LLM_PROVIDER` | LLM provider (Groq default; empty `GROQ_MODEL` = `qwen/qwen3.8-27b`) |
| `ANTHROPIC_API_KEY` (+ `ANTHROPIC_*`) | Optional Claude provider |
| `OPENWEATHER_API_KEY` | Weather in the snapshot builder |
| `SUPABASE_URL`, `SUPABASE_KEY` | Supabase client |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PERSISTENCE_ENABLED` | Direct/pooled Postgres |
| `SNAPSHOT_REFRESH_INTERVAL_MINUTES` | Scheduler interval (default 15, valid 1–60) |
| `SNAPSHOT_SCHEDULER_ENABLED` | `false` skips the background refresh (set by `tests/conftest.py`); default `true` |
| `INTERNAL_SECRET` | `/internal/refresh-snapshot` |
| `CREW_TIMEOUT_S` | 3-agent crew budget (default 45 s) |
| `VITE_API_BASE_URL` (frontend) | Empty = Vite proxy (dev); `https://floodai-8eclra.fly.dev` in production (Vercel type *Config*, not *Secret*) |

---

## Recent changes (branch `design/simplify-ui`, 2026-10)

- UI simplified for residents: readable sentence-case text, no 3D tilt, one collapsed "Lihat detail"
  section with tabs, plain-language status and evacuation copy, shorter tour.
- Removed the SOS and Keluarga pages from the frontend (Laporan came back on 2026-10-26 with photos).
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
- 2026-10-25/26: live endpoint routed through the L0–L4 engine; DSDA mm → cm at ingestion; green/red
  evacuation routes with a home destination; both maps share post and flood-area layers; home-first
  evacuation with a Google Maps handoff; Laporan page with photos; `/readyz` via Supabase; error boundary.
- 2026-10-27: floors from each post's DSDA band; v4 design, responsive bottom nav, sticky top bar,
  11-step guide; one API base; model experiment + `scripts/train_candidate.py` (candidate rejected);
  Groq model swap; chatbot prompt moved server-side (~1.8k tokens), fallback model, busy state, no
  event-loop stall; chat answers render bold/lists; Home posts classified by DSDA band; `fly.toml`
  `auto_stop_machines = 'off'`; map legend under the map on phones; `/predict/realtime-native` also returns
  `risk_interpretation_en`, so the English page has no Indonesian status text; mentors removed from Tentang.
- 2026-10-28: BPBD events counted once per RW-date and the bundle retrained; Fly scaled to one machine
  and moved from `ams` to `sin` (API ~0.4 s faster); evacuation page offers nearby shelter candidates
  from `/shelters/nearby` instead of 11 hard-coded venues (unverified phone numbers removed) on a street basemap;
  precision experiments (label gap, BPBD-label candidate rejected, stricter Danger threshold, daily
  labels); black-box FR1–FR10 and performance measured on production (thesis 5.2 and 5.5).

Full history: `git log`.
