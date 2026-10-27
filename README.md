# deFlood.ai — Informasi & Peringatan Dini Banjir Jakarta

Aplikasi web untuk warga DKI Jakarta: status banjir kota dan per wilayah, peta pos pantau air,
rute evakuasi ke rumah atau ke pengungsian terdekat (jalan hijau/merah, diteruskan ke Google Maps),
dan laporan warga dengan foto. Backend membaca
data tinggi muka air dan cuaca setiap 15 menit, menilai risiko dengan aturan deterministik berlapis
ditambah model XGBoost, lalu menyajikannya lewat FastAPI.

LLM (Groq, model `qwen/qwen3.8-27b`) hanya menulis penjelasan dan menjawab chatbot. **Keputusan status tidak pernah diambil
oleh LLM**; jika LLM gagal, sistem memakai teks templat dari nilai observasi.

Dokumentasi teknis lengkap (alur data, field API, hierarki keputusan, evaluasi model, isu yang
diketahui): [`context.md`](context.md).

---

## Arsitektur

```
DSDA DKI (Posko Banjir) ─┐
Jakarta Satu ArcGIS     ─┤                 ┌─ realtime_native (XGBoost + OOD)
BMKG cuaca + nowcast    ─┼─► snapshot ───► ├─ mesin keputusan L0–L4 (domain/decision.py)
OpenWeather (5 wilayah) ─┘   tiap 15 mnt   └─ LLM: penjelasan + chatbot (opsional)
                              │                         │
                              ▼                         ▼
                         Supabase            GET /predict/realtime-native
                                                        │
                                                        ▼
                          React + Vite (Beranda · Evakuasi · Laporan · Tentang)
```

- **Backend**: FastAPI + uvicorn (port 8080), APScheduler untuk refresh snapshot.
- **Pipeline agentik** (`pipeline/flood_pipeline.py`): Perception → Reasoning → Evaluation →
  Action → Routing, dipakai oleh `POST /predict/agentic`.
- **Frontend**: React 18 + Vite 5 + React-Leaflet (peta dasar Esri Gray Canvas), dwibahasa ID/EN,
  mode terang/gelap, responsif dari 360 px, panduan pengguna 11 langkah (tombol "?" di top bar).
  Rute evakuasi dari OSRM; jalan yang melewati titik rawan BPBD di sungai berstatus Siaga diwarnai merah.
- **Deploy**: backend di Fly.io (`fly.toml`, region `ams`; `auto_stop_machines = 'off'` supaya penjadwal 15 menit tidak ikut berhenti), frontend di
  Vercel (`vercel.json`).

---

## Menjalankan secara lokal

```bash
# Backend (Python 3.12)
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env            # isi kunci API di .env (jangan di-commit)
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload

# Frontend (terminal lain; Vite mem-proxy /predict, /api, /healthz, /shelters → :8080)
cd frontend
npm ci
npm run dev                        # http://localhost:3000
```

Snapshot pertama dibuat otomatis saat backend start. Refresh manual: `cd poskobanjir && python main.py`.
Swagger UI: `http://localhost:8080/docs`.

---

## Endpoint utama

| Endpoint | Auth | Keterangan |
|---|---|---|
| `GET /predict/realtime-native` | — | Endpoint utama yang dipakai UI |
| `POST /predict/agentic`, `POST /predict/agentic/explain` | X-Api-Key | Pipeline 5 tahap (+ penjelasan LLM) |
| `GET /predict/crew-realtime` | — | Analisis 3 agen atas snapshot terkini, di-cache per snapshot |
| `POST /api/chat` | batas per IP (10/menit) | Chatbot Groq. Prompt disusun server dari `api/chat_knowledge.txt` (~1,8k token). Kuota gratis Groq 8k token/menit per model: pindah ke model cadangan, lalu 429 `ai_busy` ("AI sedang sibuk"); kegagalan lain → basis pengetahuan offline |
| `POST /shelters/checkin` | batas per IP | Check-in tiba di pengungsian; tidak dipakai UI lagi (tombol "Saya sudah tiba" dihapus) |
| `GET /healthz`, `GET /readyz`, `GET /metrics` | — | Liveness, readiness (cek tabel snapshot di Supabase), Prometheus |
| `GET /predict/realtime` | — | **Dipensiunkan** — menjawab `410 Gone` dengan tautan ke `/predict/realtime-native` |
| `GET /reports`, `POST /reports` | batas per IP | Laporan warga (6 jam terakhir, belum diverifikasi, tidak mengubah status). Aktif kecuali `COMMUNITY_REPORTS_ENABLED=false` |
| `POST /reports/photo` | batas per IP | Foto laporan: maks. 8 MB, di-encode ulang jadi JPEG ≤ 1280 px tanpa metadata, disimpan di bucket Supabase `report-photos` |
| `/sos`, `/family/*` | — | **Nonaktif**; hanya terpasang jika `COMMUNITY_API_ENABLED=true` |

Daftar lengkap: [`context.md`](context.md#endpoints).

---

## Sumber data

| Sumber | Dipakai untuk |
|---|---|
| DSDA DKI / Posko Banjir (`datatmalaststatus.json`, `xmldata.xml`) | Tinggi muka air (dilaporkan dalam mm, dikonversi ke cm saat ingest) dan pita siaga tiap pos |
| Jakarta Satu ArcGIS FeatureServer | Pintu air dan ambang batas AWLR |
| BMKG | Prakiraan cuaca dan peringatan dini nowcast (CAP) |
| OpenWeather | Curah hujan, suhu, kelembapan (pusat + 5 wilayah) |
| BPBD DKI (Satu Data Jakarta) | Riwayat kejadian banjir per kelurahan, fitur frekuensi historis |
| BNPB (InaRISK, titik rawan banjir) | Kerentanan wilayah dan lapisan peta "daerah pernah banjir" |
| OSM / HOT InAWARE | 12.130 kandidat lokasi pengungsian |

---

## Model & evaluasi

Model yang dipakai UI: bundle `models/realtime_native_bundle/` — XGBoost, 17 fitur, SMOTE pada data
latih, kalibrasi sigmoid, deteksi OOD dengan IsolationForest.

| Metrik (data uji) | Nilai |
|---|---|
| AUC / recall / precision | 0,904 / 0,893 / 0,263 |
| PR-AUC (garis dasar 0,096) | 0,528 |
| Brier / ECE / ambang | 0,074 / 0,062 / 0,103 |

**Angka di atas optimis.** Data latih adalah 2.928 baris kecamatan-bulan (2020–2024) dengan sebagian
fitur berupa proksi (`bootstrap_proxy`), dan pembagian datanya acak terstratifikasi 68/12/20. Pada
pembagian per tahun (uji 2024), AUC 0,81 (95 % CI 0,74–0,87). Belum ada evaluasi lapangan dengan label banjir
teramati. Rincian dan sumber tiap angka: [`context.md`](context.md#model--evaluation).

Evaluasi lengkap dengan interval kepercayaan: `python scripts/evaluate_model.py`
(hasil di `artifacts/reports/model_evaluation.md`). Latih ulang: `python scripts/retrain_bundle.py`.

Eksperimen 2026-10-27 (609 varian, dipilih pada 2022–2023, diuji pada 2024): kalibrasi ulang di tahun
terbaru menurunkan ECE dari 0,19 ke ~0,03, tetapi kandidat tanpa fitur proksi + kalibrasi tahun
terbaru justru lebih buruk (AUC 0,733 vs 0,812, selisih −0,079 [−0,131; −0,026]), sehingga model yang
dipakai tidak diganti. Ulangi: `python scripts/train_candidate.py` (hasil di
`artifacts/reports/candidate_comparison.md`; bundle kandidat ke `models/candidates/`, tidak pernah
menimpa bundle yang dipakai).

---

## Variabel lingkungan

Nama saja — nilai disimpan di `.env` (lihat `.env.example`), tidak pernah di-commit.

| Variabel | Fungsi |
|---|---|
| `FLOOD_API_KEYS`, `FLOOD_API_RATE_LIMIT` | Auth X-Api-Key + batas per kunci |
| `FLOOD_IP_RATE_LIMIT`, `FLOOD_CHAT_RATE_LIMIT` | Batas per IP untuk endpoint publik (default 20 dan 10 per menit) |
| `COMMUNITY_REPORTS_ENABLED` | `false` mematikan `/reports` (default aktif) |
| `COMMUNITY_API_ENABLED` | `true` memasang kembali `/sos`, `/family/*` (default `false`) |
| `GROQ_API_KEY`, `GROQ_MODEL`, `LLM_PROVIDER`, `ANTHROPIC_*` | Penyedia LLM (`GROQ_MODEL` kosong = `qwen/qwen3.8-27b`; `llama-3.3-70b-versatile` sudah ditarik Groq) |
| `OPENWEATHER_API_KEY` | Cuaca di snapshot |
| `SUPABASE_URL`, `SUPABASE_KEY`, `DB_*` | Basis data |
| `SNAPSHOT_REFRESH_INTERVAL_MINUTES`, `SNAPSHOT_SCHEDULER_ENABLED` | Penjadwal snapshot |
| `INTERNAL_SECRET` | `POST /internal/refresh-snapshot` (cadangan dari GitHub Actions) |
| `VITE_API_BASE_URL` (frontend) | Kosong = proxy Vite; URL backend di produksi (`https://floodai-8eclra.fly.dev`, tipe *Config* di Vercel, bukan *Secret*) |

---

## Tes & CI

```bash
python -m pytest tests -q        # 572 tes backend
cd frontend && npm test          # 17 tes: rute banjir, level pos (node --test)
```

GitHub Actions (`.github/workflows/ci.yml`) menjalankan seluruh tes backend dan build frontend pada
setiap pull request dan push ke `main`, ditambah tes frontend. Tes tidak butuh kunci API: Supabase, LLM, dan scraper
di-mock, dan `tests/conftest.py` mematikan penjadwal snapshot.

---

## Lisensi

MIT
