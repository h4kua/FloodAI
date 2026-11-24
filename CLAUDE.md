# FloodAI

FastAPI backend + React frontend. Agentic flood prediction system for Jakarta.

## Stack
- Backend: FastAPI + uvicorn, port 8080
- Frontend: React + Vite
- DB: Supabase/PostgreSQL (RPC over HTTPS via `supabase` client; psycopg2 for direct/pooled access)
- ML: XGBoost + scikit-learn 1.8.0. The daily kecamatan model (`models/daily_bundle/`,
  `realtime_native/daily_model.py`) gives the decision engine its probability when it has today's
  predictions; otherwise the monthly `realtime_native` bundle (`models/realtime_native_bundle/`) does.
  No Torch.
- LLM (non-critical path): Groq `qwen/qwen3.8-27b` primary (`DEFAULT_GROQ_MODEL` in `config/llm_config.py`,
  `GROQ_MODEL` overrides), Anthropic Claude optional — explanation and chat only. Chat prompt lives in
  `api/chat_knowledge.txt` (core rules + only the sections the question touches, ~1.5k tokens); the
  free tier allows 8k tokens/min per model, so `/api/chat` falls back to `openai/gpt-oss-20b`, waits out
  a retry-after of ≤ 3 s once, then answers 429 `ai_busy`
- Deploy: Fly.io (backend, `fly.toml`) + Vercel (frontend, `vercel.json`)

## Run
```
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
```

## Architecture
5-stage agentic pipeline (`pipeline/flood_pipeline.py`):
Perception → Reasoning (XGBoost + OOD) → Evaluation (decision engine L0–L4) → Action → Routing.
On the live path (`/predict/realtime-native`) a learned decision layer (`realtime_native/decision_layer.py`,
authority `L3_LEARNED`) replaces the hand-written middle layers (L1.5, L1.8, L1.9, L2, L3, L3.1, L3.3, L3.7, L4)
behind the safety rules L0, L1 (Siaga 1, rapid rise) and L1.7 (BMKG severe); without its inputs the full
rule hierarchy decides, as before (`LEARNED_DECISION_ENABLED=false` forces that).
The LLM is NOT in the critical path — decisions are deterministic; the LLM only generates the
Bahasa Indonesia explanation and falls back to a static template on failure.

## Key paths
- API: `api/main.py`
- Agentic pipeline: `pipeline/flood_pipeline.py`
- Decision engine: `services/decision_engine.py` (the former `app/` package was flattened)
- Output contract / canonical enums: `core/output_contract.py`, `contracts/vocabulary.py`
- Tests: `tests/` (679, `python -m pytest tests -q`); frontend `npm test` in `frontend/` (36: flood roads, shelter ranking,
  post levels, weather per wilayah, daily model card, learned-layer status sentence, Siaga 2/1 map areas, layer reasons)
- Frontend: pages Beranda / Evakuasi / Riwayat / Laporan / Tentang; API base in `frontend/src/lib/api.js`;
  onboarding guide `components/OnboardingTour.jsx` (12 steps, reopened from the top-bar "?"); charts are plain SVG
  (`components/charts.jsx`, no chart library)

## Data ingestion
- Live water levels: Jakarta Satu ArcGIS FeatureServers via `services/pintu_air_fetcher.py`
  + `services/awlr_threshold_fetcher.py` (clean JSON, no browser). Refresh: `scripts/run_tma_scraper.py`.
- The legacy TMA scraping-proxy + Selenium DOM scrape (`services/data_ingestion/tma_scraper.py`)
  is intentionally DISABLED (no `TMA_PROXY_URL`); it degrades to STALE, never crashes.
- Weather/alerts: OpenWeather + BMKG.

## Known issues
- Calibration penalty deactivated (`services/decision_engine.py`). No valid field ECE exists for
  the current realtime-native bundle: 0.062 (`artifacts/reports/model_evaluation.md`) is its
  bootstrap-proxy random test split and optimistic (the 0.0183 in `training_stats.json` came from an
  ECE function that mixed quantile and equal-width bins, fixed 2026-10-24); 0.1962 (`artifacts/configurations/calibration_cache.json`,
  labels derived from the model's own ranking) and 0.3784 (`artifacts/reports/scenario_validation.json`,
  n=7) come from older model versions.
- Bundle retrained 2026-10-28 (`scripts/retrain_bundle.py`) with the leak-free
  `kecamatan_historical_flood_freq` (per row, events from earlier years only; inference uses
  years before the snapshot's year), now from BPBD events counted once per RW-date (the workbooks
  list one row per RT; 4,667 events 2020–Mar 2026, was 7,301). Test AUC 0.899 / recall 0.875 /
  precision 0.282 / threshold 0.126. Previous bundles stay in git history (5919525 and earlier).
  Changing `data/bundled/kelurahan_flood_history.json` changes a model input: retrain after rebuilding it.
- The split is still a RANDOM stratified 68/12/20 (train 1990 / val 352 / test 586, 56 test
  positives): the chronological validation slice (May 2023–Jan 2024) has 0 positives, so training
  falls back to random (the report now says so). Test rows are spread over 2020–2024, so the
  metrics above are optimistic. By-year estimate (train 2020–2022, val 2023, test 2024 with 22
  positives): AUC 0.83 [0.75–0.89], PR-AUC 0.12 (no-skill 0.04), ECE 0.17. Run
  `python scripts/evaluate_model.py` for the current figures with 95 % bootstrap CIs.
  Training flood labels shrink sharply over time (117/78/54/11/22, 2020–2024), but BPBD records do not
  (267/147/213/113/155): the drop comes from the label source (see the label gap below).
- No observed row-level flood labels for evaluation: `realtime_feature_history.csv` has no label
  column; `calibration_labeled.csv` labels are synthetic.
- Live history: until 2026-11-05 the server kept only `realtime_snapshot_store` id `latest` (the history
  writers need `DB_*` secrets that Fly lacks). Each refresh now also upserts a compact
  `history:<fetched_at_utc>` row there (~12 KB, ~220 MB per 6 months: watch the free 500 MB quota).
  Older history is only the local `realtime_feature_history.csv`: 1,192 rows on six days (24–26 Apr,
  9–10 May, 16 May 2026), none on the May 2026 BPBD flood days. `FEATURE_HISTORY_DB_ENABLED=false` on Fly,
  so the model's lag features still start empty (as before).
- Hourly rain (2026-11-05, `scripts/hourly_rain_experiment.py`, kecamatan-days 2020–Sep 2025 vs BPBD dates):
  the wettest-hour features add nothing over daily totals, with ERA5 or with GPM IMERG (95 % CIs
  include 0). The rain SOURCE matters: on the same rows IMERG beats ERA5 (`scripts/rain_source_comparison.py`;
  test 2023–Sep 2025 PR-AUC 0.09 → 0.17, ROC-AUC 0.80 → 0.83–0.84, CIs exclude 0 in 3 of 4 runs).
  On 1 Jan 2020 ERA5 gives 31 mm, IMERG 101 mm (Halim gauge 377 mm). IMERG comes from
  `scripts/fetch_imerg_history.py` (Giovanni time-series API, `EARTHDATA_TOKEN` in .env; the Earthdata
  account must approve "NASA GESDISC DATA ARCHIVE"), cached in data/raw/imerg/. IMERG Final lags ~3.5
  months (V07B ends 2025-09-30); serving would need IMERG Early (~4 h latency).
- IMERG candidate (2026-11-05, `scripts/train_imerg_candidate.py`, `artifacts/reports/imerg_candidate.md`): the
  served pipeline retrained by year with the cleaned dataset's two rain columns swapped for IMERG. On the
  dataset label IMERG is worse (AUC 0.71 vs 0.83; the dataset's max_rainfall correlates only 0.39 with
  IMERG, so that label likely follows the dataset's own rain). On BPBD labels IMERG without the proxy
  features is the best point estimate (AUC 0.787 vs 0.760, PR-AUC 0.61 vs 0.56; at the served Danger rule
  recall 0.59 / precision 0.50 / 182 alarms vs 0.51 / 0.53 / 149) but the paired 95 % CIs include 0.
  The served bundle stays.
- 2026 flood events: `data/processed/bpbd_updates_2026.csv` holds BPBD flooded-RT figures per kelurahan
  quoted by news (1–25 May 2026 only); bpbd.jakarta.go.id posted no genangan updates 24 Apr–5 Nov 2026.
- AUC 0.9452 belongs to the legacy Jakarta model (`flood_model_jakarta.pkl`, random 80:20 split).
  Its endpoint `/predict/realtime` was retired 2026-10-24 (410 Gone); the UI uses `/predict/realtime-native`.
- BNPB district mapping gap (kecamatan write-back); InaRISK falls back to bundled static JSON.
- Model experiment 2026-10-27 (by year, test 2024): 609 variants; logistic regression without the proxy
  features ranked floods better (PR-AUC 0.27 vs 0.10) but no variant beat the served model's precision at
  ~86 % recall. The XGBoost candidate without proxies + Platt on the latest year (`scripts/train_candidate.py`,
  `artifacts/reports/candidate_comparison.md`) is worse: AUC 0.796 vs 0.826 after the 2026-10-28 event-count
  fix (was 0.733 vs 0.812). The served bundle stays.
- Label gap (2026-10-28, `scripts/precision_experiments.py`): the training `banjir` label covers only
  276 of the 895 kecamatan-months with a BPBD flood (2020–2024); against BPBD records the by-year
  model's 2024 precision is 0.53, not 0.13. A BPBD-labelled model (by year AUC 0.76, PR-AUC 0.50,
  no-skill 0.26) was built as a bundle (`scripts/train_bpbd_candidate.py`) and rejected: its thresholds put
  57 % of 2024 kecamatan-months at Bahaya and it is not more precise at equal alarm volume. Daily rainfall alone does not predict flood days
  (`scripts/daily_flood_experiment.py`). BPBD per-kelurahan events exist from 2013 (`events_clean.csv`);
  training stops at 2020–2024 only because the features do.
- Fly stopped/suspended both machines despite `min_machines_running = 1`, halting the 15-minute
  scheduler. `fly.toml` has `auto_stop_machines = 'off'` (live since 2026-10-27) and the app runs one
  machine (`6837171a569698`, region `sin`); the GitHub backup cron still needs repo secrets `REFRESH_URL` +
  `INTERNAL_SECRET` (and `INTERNAL_SECRET` on Fly).
- Groq free tier: 8k tokens/min per model, so roughly 4–8 chat questions a minute across all users;
  heavier use needs a paid tier.

- Thesis experiments (2026-11-10, `scripts/thesis_experiments.py`, GPU, `artifacts/reports/thesis_experiments.md`):
  a daily kecamatan model of our own on BPBD flood dates + IMERG rain (train 2020-2021, validate 2022, test 2023 to
  Sep 2025, test prevalence 0.024). Tuned XGBoost test ROC-AUC 0.839 [0.819-0.857], PR-AUC 0.162 vs rain-that-day
  0.743 / 0.082 (paired CIs exclude 0); logistic regression and random forest are as good (CIs include 0); place and
  season lift AUC 0.72 -> 0.83, the model family does not. At equal alarm volume it catches 32 % of floods vs 22 % for a
  rain threshold. Rules vs model vs hybrid on real 2025 DSDA daily water levels (`data/raw/tinggi-muka-air-...xls`, 19
  posts, every day of 2025): hybrid catches more flood days than rules alone (>= Alert recall 0.32 -> 0.45, CI of the
  difference [0.075, 0.186]) at lower precision (0.84 -> 0.64). Drivers from the literature (`scripts/fetch_flood_drivers.py`,
  `scripts/driver_ablation.py`: ERA5-Land soil moisture, MJO OMI, ENSO ONI, northerly wind, spring tide) add nothing
  same-day beyond rain; day ahead (no same-day rain) they lift ROC-AUC 0.78 -> 0.80 (CI [0.001, 0.041]) but not on 2022.
  Nothing is served yet.
- `data/bundled/awlr_stations.json` (AWLR FeatureServer) holds Siaga limits on another scale for several posts
  (Manggarai Siaga 1 250 cm vs 950 cm in the live DSDA feed; Depok has Katulampa's 80/150/200). The live app reads the
  feed's own limits and is not affected; experiments use `data/bundled/dsda_siaga_limits_2026-11-10.json`. In the 2025 file,
  Marina (Laut/Kali), Ancol Flushing and PA. Hek sit at Siaga 3+ on more than half of the days.

- More data and longer tests (2026-11-11). IMERG now 2013 onward (`fetch_imerg_history.py --history`), so BPBD dated
  events 2013-2019 (`events_clean.csv`) train the daily model; `scripts/long_experiments.py` tests every year 2016-2025 on
  models trained on earlier years only: XGBoost F4 ROC-AUC 0.841 [0.822-0.858] pooled 2016-2022 and 0.869 on 2023-Sep 2025
  (rain alone 0.75 / 0.74); XGBoost beats logistic (+0.008-0.053); hourly intensity and the literature drivers add nothing.
  DSDA water levels 2016-2021 from Satu Data Jakarta (`scripts/fetch_satudata_tma.py`, 2.2 M readings with the official
  status_siaga; the 2020 dataset also holds Aug-Dec 2021; 2016-2017 are patchy) -> `scripts/dsda_history.py` ->
  `data/processed/dsda_tma_daily_2016_2020.csv`. `scripts/water_level_experiments.py`: city water features lift the
  kecamatan model on 2019-2021 (ROC-AUC 0.778 -> 0.810, PR-AUC 0.078 -> 0.131, CIs exclude 0). Rules on every river post
  warn on 94 % of days: P.A. Hek, Jembatan Merah and Istiqlal sit at Siaga 3+ on 58-94 % of days (gate-operated); without
  them the rules warn on 47 %. A depth-3 learned decision layer + Siaga-1 safety rule matches the informative-post hybrid at
  Watch/Alert and catches more large floods at Danger (recall 0.71 vs 0.58, CI [0.026, 0.242]); at equal warning days no
  approach ranks days significantly better than the official statuses. PetaBencana: flooded-area archive is open but ends
  Oct 2022 with no public area map; the reports archive needs a key (`scripts/fetch_petabencana_reports.py`, PETABENCANA_API_KEY
  in .env, request at info@petabencana.id).

- Daily model candidate (2026-11-12, `scripts/daily_model_candidate.py`, `artifacts/reports/daily_model_candidate.md`):
  XGBoost F4 out of sample per year, isotonic map fitted on earlier years only: ECE 0.169 -> 0.0055 (2017-2025, every
  year 0.005-0.019), Brier 0.094 -> 0.021; alarm-budget thresholds Waspada 0.051 / Siaga 0.092 / Bahaya 0.141.
  Bundle (not served, gitignored folder) `models/candidates/daily_f4/` with model_card.json. City-wide water features are
  enough: per-post status + location adds nothing (`scripts/local_water_experiment.py`). IMERG Early (and Late) answer
  from Giovanni about a day behind (`GPM_3IMERGHHE_07_precipitation`), so live serving is possible. Chapter 5 draft:
  https://claude.ai/artifact/Nwsqz6vKWR8t975ETZHQPx

- News-derived flood days (2026-11-12, `scripts/fetch_news_flood_days.py` -> `data/processed/news_flood_reports_*.csv`,
  `scripts/news_label_experiment.py`, `artifacts/reports/news_label_experiment.md`): detik.com reports quoting BPBD,
  mapped to the 42 kecamatan (noisy: some articles are about other cities, so only days inside a BPBD-flooded
  kecamatan-month are kept). They add 320 flood kecamatan-days to 2023-Sep 2025 (990 -> 1310); training on them changes
  nothing (ROC-AUC 0.869 vs 0.865, CIs overlap). Nothing served; the raw cache (data/raw/news/) is not committed.

- Large flood days (2026-11-17, `scripts/large_flood_experiment.py`, `artifacts/reports/large_flood_experiment.md`): can the
  live daily model (lag 1/2) justify Siaga on days with BPBD floods in >= 5 kecamatan (6.8 % of days 2016-2022)? It ranks
  them better than "any flood" (lag 1 ROC-AUC 0.74 vs 0.70; 2023-2025 0.80) but is not precise enough: at 2 alarm days a
  month, lag 1, 26 % of alarm days are large floods (2016-2022; 32 % in 2023-2025) and half have no flood at all. Sum of
  kecamatan probabilities = max (CIs include 0); a city model trained on the large label is worse. For comparison the
  informative-post water rules at Alert: any-flood precision 0.70. Siaga/Bahaya stay with the water-level rules; the
  model stays capped at Waspada.

- Decision-layer experiments (2026-11-17, `scripts/decision_layer_experiments.py`, `artifacts/reports/decision_layer_experiments.md`;
  lag 1, test 2019-2021 + 2025, nothing served). (1) Today's rain so far (IMERG half-hours that started by H-5 h) + the hour:
  ROC-AUC 0.786 vs 0.775 (CI of the difference [-0.01, 0.033]) but Siaga recall 0.174 -> 0.22 ([0.006, 0.085]) and Bahaya
  0.082 -> 0.117 ([0.01, 0.064]) at higher precision (0.74 -> 0.76, 0.77 -> 0.84), and fewer Waspada (44 % -> 36 % of
  snapshots, precision 0.38 -> 0.43). (2) One status per wilayah: a layer with the wilayah's highest kecamatan chance and its
  own river posts beats the city level copied to every wilayah: ROC-AUC 0.803 vs 0.762 ([0.026, 0.057]); Siaga recall +0.04-0.12
  and precision +0.05-0.14, Bahaya both better; more Waspada. (3) Ablation: the daily model matters most (ROC-AUC -0.02 to
  -0.05 without it), upstream posts a little, yesterday's posts not significantly; the served chance runs low in the 10-40 %
  range (mean 0.14 -> 0.27 observed; ECE 0.075, 0.17-0.18 in 2020 and 2025). (5) Lead time, 46 flood days 2020-2021 with BPBD
  + news (first report ~12:00 WIB median): Waspada before the first report on 85 % (learned, median 16.7 h) vs 83 % (rules,
  13.1 h); Siaga 30 % vs 22 % (CI [-0.022, 0.217]). Snapshot spacing is 5-7 h, so leads are coarse.
- Live validation (`scripts/live_validation.py`, `artifacts/reports/live_validation.md`): replays the 15-minute history rows
  through the served code and compares each day's highest level with news-reported floods
  (`fetch_news_flood_days.py --start 2026-11 --end <month> --out data/processed/news_flood_reports_2026.csv`). 5-17 Nov 2026:
  no flood reported; Waspada on 7 days (learned) and 7 (rules), not the same days. Re-run monthly through the season.

## Resolved
- 2026-11-24: five resident features. (1) Riwayat page (`pages/History.jsx`, `GET /history/summary`): the status and the
  learned layer's chance over 7/14/30 days, warning periods, IMERG rain per day (`daily_model.rain_summary`) and each river
  post's highest Siaga band per day. The API scheduler logs every 15-minute decision as a `decision:<fetched_at>` row in
  `realtime_snapshot_store` (`services/history_service.log_decision`); the days before were replayed with
  `scripts/backfill_decision_log.py` (marked `source: replay`). (2) "Bagaimana keputusan dibuat" in the AI tab
  (`DecisionPathCard`): data in, safety rules L0/L1/L1.7, the layer's chance against its thresholds and what raised it.
  (3) A post's popup on the home map loads its last 2 days of water level (`PostTrend`, `GET /history/post`); popups open in
  Leaflet's popup pane and re-pan once they grow (`keepPopupInView`; they were cut off at the map's top edge and drawn under
  the other posts). (4) "Cek daerahku" under the status (`AreaCheck`, `frontend/src/data/areaProfiles.json` from
  `scripts/build_area_profiles.py`: BPBD flood days 2013-2025 per kecamatan and kelurahan; a kelurahan with under a fifth of
  its days in another kecamatan is moved to its main one, e.g. Kampung Melayu Duren Sawit 4 -> Jatinegara), with today's
  kecamatan chance, nearest posts and shelter candidates, "Pakai lokasi saya", remembered in localStorage only.
  (5) Telegram alerts (`services/telegram_alerts.py`): a message when the status rises to Siaga/Bahaya
  (`TELEGRAM_MIN_LEVEL`) and when it falls again; needs Fly secrets `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`, the Riwayat
  page shows a join card when Vercel has `VITE_TELEGRAM_URL`. Also: the status card lists what to do at each level, trend and
  rain are plain text (were pills), and the chat button sits above the bottom nav up to 768 px (it covered "Tentang").
  Follow-ups the same day: `/history/summary?days=7` ran the 512 MB machine out of memory (a week of full post lists
  loaded at once): post history is now streamed 100 rows a page, each finished WIB day's bands are kept in memory
  (`_day_bands`, cold 14 days ~14 s / 64 MB, then 0.5 s) and the scheduler warms them. Map popups near the edge (Marina
  Ancol on the coast) were still cut off because `maxBounds` with viscosity 1 blocked the pan: `PopupKeeper` (both maps)
  lifts the bounds while a popup is open and restores them when the last one closes, and re-pans when a popup grows.
  Weather cards stay inside the map (`KeepCardsInside`), show only kota + temperature on phones and lost the glass blur;
  labels are sentence case, only the status card animates in, the chat button lost its permanent fake "1" badge.
- 2026-11-17: status per wilayah (`scripts/train_wilayah_layer.py`, `artifacts/reports/wilayah_layer.md`, `models/daily_bundle/wilayah_layer*.json`,
  `decision_layer.decide_wilayah`, API field `wilayah_status`). Inputs: the city layer's + the kota's highest kecamatan chance
  + its own river posts now / yesterday (`posts_d1` in the daily state) + which kota; a kota or upstream post at Siaga 1 -> Bahaya
  there. It does not change the city status. Served thresholds = the city layer's chance thresholds (same meaning everywhere);
  volume-matched thresholds (6 % Waspada, 38 % Bahaya) put South Jakarta at Bahaya on calm November days and were dropped.
  Test lag 1 (2019-2021 + 2025) vs the city level copied to every kota: ROC-AUC 0.817 vs 0.779 (CI [0.026, 0.051]); precision
  Waspada 0.36 vs 0.18, Siaga 0.67 vs 0.38, Bahaya 0.67 vs 0.48, but recall lower (Siaga 0.14 vs 0.29) and Waspada on 12 % vs
  36 % of kota-snapshots. Live replay 6-17 Nov: Selatan Waspada 22 %, Timur 11 %, others <= 3 %. The API still returns
  `wilayah_status`, but the Beranda does not show it: the user wanted the flood chance on the map's flood-prone areas instead,
  so `WilayahStatus` is back to the worst post per kota. About page rewritten for the daily model, the learned layer, the
  safety rules, the map circles and the year-by-year test figures.
- 2026-11-18: home-map red circles meant "a post on this river is at any Siaga", so a chronic Siaga 3 (Cengkareng Drain)
  lit areas whose kecamatan chance was 4 %; a % chip per kecamatan (tried 2026-11-17) cluttered the map and was removed.
  `scripts/active_area_chance.py` applies the map's activation rule to the DSDA archive 2016-2021 (gate posts left out):
  areas along a river had a BPBD flood on 1.7 % of normal days, 12 % at Siaga 3, 25 % at Siaga 2, 20 % at Siaga 1 (CI
  [0.04, 0.43], 26 days) -> `frontend/src/data/activeAreaChance.json`. The home map now draws red circles only for posts at
  Siaga 2 or 1 (`activeFloodPoints(..., { minRank: 2 })`) and each popup gives that rate; the evacuation page keeps Siaga 3
  (routes stay cautious). No signal makes a flood certain: the strongest is about 1 day in 4.
- 2026-11-17: the learned decision layer also reads today's rain so far: IMERG Early half-hours that started by now - 5 h
  (mean and max over the model's kecamatan cells, Bogor), plus the WIB hour (the only input not monotone). `daily_model.refresh()`
  keeps today's half-hours per cell in the state (`today_halfhours`); without them the rules decide. Lag 1, test 2019-2021 +
  2025 vs the rules: ROC-AUC 0.786 vs 0.694; Siaga recall 0.13 -> 0.22 at precision 0.76, Bahaya 0.05 -> 0.12 at 0.84, Waspada
  36 % of snapshots (was 44 % without today's rain) at precision 0.43. Thresholds lag 1: Waspada 20 %, Siaga 65 %, Bahaya 80 %.
  Live replay 5-17 Nov: Waspada 31 % of snapshots (rules 42 %).
- 2026-11-17: learned decision layer (supervisor: the 10 hand-written layers were too simple). `scripts/train_decision_layer.py`
  builds city snapshots at 06/12/18/23 WIB from the raw DSDA readings 2016-2021 (latest reading of the 3 h before) and the
  2025 daily file: the daily model's out-of-sample city chance + the 14 river posts now and yesterday; label = BPBD flood
  in any of the 42 kecamatan that day. Compared tree (depth 3), logistic regression and XGBoost (depth 2, all inputs
  monotone increasing), test years 2019-2021 + 2025 each trained on earlier years. Served: monotone XGBoost per lag
  (`models/daily_bundle/decision_layer*.json`), thresholds = flood chance at which it raises each level as often as the
  rules did on the training snapshots (lag 1: Waspada 21 %, Siaga 61 %, Bahaya 76 %). Lag 1 vs the rules (river posts +
  daily Waspada): ROC-AUC 0.775 vs 0.694 (CI of the difference [0.05, 0.115]); Siaga recall 0.129 -> 0.174 (CI
  [0.007, 0.08]) and Bahaya 0.051 -> 0.082 ([0.017, 0.046]) at unchanged precision (0.74, 0.77); Waspada catches more
  (0.56 -> 0.76) but fires more (27 % -> 44 % of test snapshots) at lower precision (0.46 -> 0.38); at equal alarm volume
  on the test rows no level differs significantly. The depth-3 tree was too coarse (8 scores; Siaga precision 0.72 ->
  0.46). Snapshots without yesterday's posts are dropped and a missing reading counts as normal (XGBoost had learned
  "missing -> higher risk"). Live replay 6-17 Nov 2026: Waspada 42 % of snapshots (rules 45 %), but on other days: calm
  posts lower a 21 % daily chance to Aman, a post at Siaga 3 yesterday raises a 6 % one to Waspada. The interpretation
  and the Beranda sentence give today's chance, the level thresholds and what raised it most (XGBoost contributions).
  Also: one GES DISC file listed before OPeNDAP serves it no longer drops the whole file fill.
- 2026-11-17: the daily model reads the newest rain straight from the GES DISC IMERG Early files (OPeNDAP subset of the
  9 model cells, ~2 s a file, ~4.5 h after the rain; `imerg_client.fetch_recent`) for the hours after Giovanni's last
  value. Same values as Giovanni (all 9 cells, every half-hour of 15 Nov). Giovanni's delay varies (~28 h on 13 Nov,
  ~9 h on 17 Nov), so yesterday's rain (lag 1, ROC-AUC 0.808 / 0.836 vs lag 2 0.786 / 0.799) is now complete from about
  05:00 WIB every day instead of ~09:00 WIB on a good day and the next day on a bad one. A file failure keeps Giovanni
  alone. Refresh ~28 s cold, ~13 s after; files stay cached in memory (Early files do not change).
- 2026-11-13: the daily kecamatan model is on the site (`scripts/train_daily_live_model.py`,
  `artifacts/reports/daily_live_model.md`, bundle `models/daily_bundle/`). Rain is IMERG Early, which Giovanni serves
  ~28 h late, so it uses rain through D-2 (D-3 before ~04:00 WIB; D-1 when complete) plus the city's river-post Siaga
  status on D-1/D-2 from our own history rows (14 fixed river posts in both the 2016-2021 archive and the live feed;
  coastal and gate posts left out). Rolling by year: kecamatan ROC-AUC lag 2 0.786 (2016-2022) / 0.799 (2023-2025) vs
  place+season 0.735 / 0.769 (CI of the difference excludes 0); water adds nothing significant; lag 1 is 0.808 / 0.836.
  City probability = highest kecamatan (isotonic-calibrated on out-of-sample predictions). City precision is ~0.31-0.36
  at every threshold (base rate 0.22), so the model raises at most Waspada (8 model days a month; Siaga/Bahaya
  thresholds 1.0) and is exempt from the L3.1 precision gate (its absolute 0.15 margin covered the model's whole range).
  `daily_model.refresh()` runs every 30 min in the API scheduler (16 s; never in a request) and needs `EARTHDATA_TOKEN`
  on Fly; without it, or when no rain day is complete, the monthly model serves as before (`DAILY_MODEL_ENABLED=false`
  switches it off). The response carries `daily_model` (per kecamatan) and `realtime_native_probability`; the AI tab
  shows the top-5 card and a model-raised Waspada says "hujan beberapa hari terakhir ...". Also fixed: signal conflict 4
  escalated when the MODEL was above the baseline (comment said the reverse); now only a baseline above the model
  escalates. The isotonic ECE ~0 is in-sample on the out-of-sample predictions, so optimistic.
- 2026-11-12: the city status sat at Waspada or higher 92 % of the time (live history 5-12 Nov, 723 snapshots):
  P.A. Cengkareng Drain was at Siaga 3+ in 89 % of snapshots, Pompa Pasar Ikan in 55 %, Marina Ancol (Laut) in 48 %
  (the last two follow the tide). These posts now count one band lower for the CITY status only
  (`services/hydrology_analyzer.status_siaga_level`; Siaga 3 -> normal, 2 -> Siaga 3, 1 -> Siaga 2; override or switch off
  with `FLOOD_CHRONIC_POSTS`); each post keeps its official DSDA status on the map, list and area cards. Replayed on the
  history: Aman 8 % -> 67 %, Waspada 67 % -> 33 %, Siaga 25 % -> 0 %. `stations[].chronic` marks them, and the Aman
  sentence says such a post "memang sering di Siaga 3". In 2016-2021 data, dropping always-on posts cut Watch recall
  0.99 -> 0.72 (large floods 0.99 -> 0.93), so some small floods no longer get Waspada.
- 2026-11-06: the chat answered anything (it wrote Python code on request): `api/chat_knowledge.txt` now opens with a
  SCOPE RULE (floods, weather, evacuation, the site only; otherwise a one-sentence refusal in the user's language).
  Checked live on gpt-oss-20b: code, homework, recipes, translation and "ignore your rules" are refused; flood questions answered.
- 2026-11-06: home map weather per wilayah ("Cuaca per wilayah" switch, on by default): the backend's OpenWeather
  reading per kota (`openweather_wilayah`, the same data as the "Weather now by area" cards; the map first read
  Open-Meteo and the two disagreed) in nine states (`frontend/src/lib/wilayahWeather.js`). Each kota
  (`frontend/src/data/wilayahShapes.json` from `scripts/build_wilayah_shapes.py`, OSM via Nominatim) gets a tint and
  layered SVG-pattern textures (`components/WeatherLayer.jsx`: sun glow, stars, clouds drifting with the wind, mist,
  rain in two depths, a soft storm glow; still under prefers-reduced-motion, paused off screen) and a glass card in
  the cards' own words; tapping it opens See details > Weather on that kota (details: feels-like, humidity, cloud,
  wind). Weather does not feed the flood status. The home map's street-map switch was removed.
- 2026-11-05: map rivers and flood-prone areas. A clicked post lights up its river (`frontend/src/data/postRivers.json`
  from `scripts/build_post_rivers.py`: traced on the OSM waterway network from the piece touching the post, 8 km,
  connected only; a stretch under 1 km is re-traced from every waterway within 40 m of the post, as Kaliduri's was
  40 m; upstream posts outside the Jakarta map come from Overpass around the post, cached in data/raw/overpass/, and
  are marked `upstream`, so they still activate their whole river; Cipinang Hulu stands ~800 m off its channel and
  gets a dashed `link`; only Pompa Pluit has no line). A Siaga post now activates only the BPBD points within
  1 km of that drawn stretch (`activeFloodPoints(..., riverTable)`), not every point on its river (Cengkareng
  Drain 10 -> 5). 8 of 154 BPBD points lay 3.4-11 km from their own kelurahan (Srengseng in Kalideres); they sit at
  the kelurahan centre now, marked `relocated` (`scripts/check_flood_prone_points.py`, Nominatim cache in
  data/raw/). English page: wilayah names (North ... East), forecast columns as days, 3-agent analysis in English
  (`/predict/crew-realtime?lang=en`, cache per language).
- 2026-11-05: chat sometimes looped on unrelated text ("Selalu tanyakan kapan kamu membutuhkan ..."): replies now use
  temperature 0.3, a reply that repeats a sentence goes to the fallback model (`_looks_degenerate` in
  `api/routes/chat.py`), looping replies are dropped from the history, and posts carry their wilayah. The 3-agent
  analysis was 1-2 short lines: its hydrology context read keys the DSDA feed lacks (every post "Unknown ...
  (Normal)", first six only); it now lists the most critical posts by name, kota, trend and Siaga limits, the
  experts write 3-4 sentences with numbers and the panel shows them. The evacuation list offers only the 5
  nearest shelters outside active flood-prone areas (`nearestShelters`, risky ones only fill a short list; since 2026-11-06); routes to a place within 3 km
  are walked (FOSSGIS `routed-foot`, car OSRM as fallback; Google Maps opens in walking mode); the route notes when red stretches only touch a start or end inside a
  flood-prone area. Local `.env` still sets GROQ_MODEL to the withdrawn llama model (Fly does not).
- 2026-11-05: `scripts/parse_rekap_kejadian_banjir.py` dropped every row under a "KAB. ADM. KEP. SERIBU"
  header (64 rows in Nov–Dec 2025, 15 in 2024) and filed 23 island rows of 2020–2021 under Jakarta
  Barat/Timur. Fixed (needs openpyxl, not in requirements.txt), island names unified ("P. Pari" →
  "PULAU PARI"). The 42 model kecamatan keep the same flood frequency, so no retrain.
- 2026-10-28: the evacuation page offered only 11 hard-coded venues (with unverified phone numbers) and a
  grey basemap without small streets. It now asks `GET /shelters/nearby` for ~20 of the 12,130
  OSM/InAWARE candidates in `data/bundled/jakarta_shelters.json` (no hospitals/clinics, same-name
  duplicates within 150 m dropped), lists those in an active flood-prone area last (`rankSheltersByFlood`),
  keeps 3 large venues as farther options and offline fallback, and uses Esri World Street Map (zoom 19).
- 2026-10-29: BPBD flags on shelter candidates (`scripts/build_shelter_flags.py` → `data/bundled/shelter_flags.json`):
  14 of 61 BPBD evacuation sites (2018, matched by name within 3 km of their kelurahan) and 105 schools on
  BPBD's flood-prone list (matched within 200 m by school number). `/shelters/nearby` returns `bpbd_site`
  and `flood_prone_school` and adds BPBD sites within 3 km; the page lists BPBD sites within 1 km first and
  flood-prone schools last. The home map has a "Peta jalan" switch (default stays Gray Canvas, so status
  colours do not clash with the street map's yellow/orange roads).
- 2026-10-28: backend moved from `ams` to `sin` (machine cloned, old one destroyed, `primary_region = 'sin'`).
  From Singapore: `/predict/realtime-native` median 1,012 → 573 ms (max 10.4 s → 0.95 s), `/healthz`
  465 → 324 ms, `/readyz` 1,104 → 505 ms; status + map on a repeat visit ~0.5–0.8 s. Black-box FR1–FR10
  all pass on production (thesis 5.2).
- 2026-10-24: served model = trained model. The native export kept only fold 0's booster and
  applied all five calibrators to it (per-prediction gap up to 0.32); it now ships one booster per
  calibration fold (`xgboost_model_fold{i}.json`), parity < 1e-6. Calibration method is chosen on
  the validation fold (was the test fold); threshold selection no longer returns 1.0 (recall 0) when
  no threshold reaches the precision floor.
- 2026-10-24: `POST /api/chat` rate-limited per IP (`FLOOD_CHAT_RATE_LIMIT`, Fly client IP from
  `Fly-Client-IP`); `/reports`, `/sos`, `/family/*` off unless `COMMUNITY_API_ENABLED=true`;
  CI in `.github/workflows/ci.yml` (pytest + frontend build).
- 2026-10-27: Groq withdrew `llama-3.3-70b-versatile` (model_not_found → chat always offline); default is
  now `qwen/qwen3.8-27b`. AI answers render bold/lists in the chat bubble.
- 2026-10-27: DSDA water levels arrive in mm and are converted to cm at ingestion (`dsda_mm_to_cm`);
  the L1/L1.8 floors use each post's own DSDA band; `/readyz` checks Supabase; community reports with
  photos (migration 110, bucket `report-photos`); Fly secrets re-imported (were the literal "...").
- 2026-10-27: chat prompt moved server-side (`api/chat_knowledge.txt`, ~5k → ~1.8k tokens), model
  fallback, Groq call off the event loop (one slow answer stalled every request), 429 shown as "busy".
- 2026-10-27: Beranda gauge, Siaga line, wilayah cells and map classify posts by their DSDA band
  (`postRiskLevel` in `frontend/src/lib/dashboardHelpers.js`), like the engine; the ratio is a fallback.
- 2026-10-27: report reactions — likes/dislikes per device, comments, ⋯ menu (share, copy link, Google Maps,
  report); 3 flags hide a report; `/?report=<id>` deep links. Needs `db/migrations/111_report_interactions.sql`
  run in Supabase (until then the endpoints answer 503 and counts show 0).
- 2026-10-27: English page fully English except the 3-agent deep analysis (prompts ask for Indonesian):
  `/predict/realtime-native` returns `risk_interpretation_en` beside `risk_interpretation`. On phones (≤ 640 px)
  the map legend sits under the map, always open. Mentors removed from the About page.
- 2026-10-27: Vercel `VITE_API_BASE_URL` pointed at the old `floodai.fly.dev`; it is now
  `https://floodai-8eclra.fly.dev` (type Config). `html/body` use `overflow-x: clip` so the top bar stays sticky.
- DB CHECK-constraint naming drift (orphan `chk_eval_status` blocked `CONFLICT`/`LOW_TRUST`
  persistence) — fixed by `db/migrations/106_fix_status_constraint_naming_drift.sql`, applied
  to Supabase 2026-06-19.
