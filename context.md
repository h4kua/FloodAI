# deFlood.ai — Session Context

> Paste di awal new session supaya Claude langsung paham state proyek.

---

## Identitas Proyek

**Nama produk:** deFlood.ai  
**Repo:** `D:\FloodAI - Copy` (local) · `github.com/h4kua/FloodAI` (remote, branch `main`)  
**Commit HEAD:** `b40bb70` — fix: chatbot EN language + GPS map + About clean + nav panel  
**Deploy:** Backend → Fly.io (`https://floodai.fly.dev`) · Frontend → Vercel  
**Dibuat oleh:** @juanvier_

---

## Stack

| Layer | Teknologi |
|---|---|
| Backend | FastAPI + uvicorn, port 8080 |
| ML | XGBoost + scikit-learn 1.5.2 |
| AI Chat | Groq API (`llama-3.3-70b-versatile`) |
| Database | Supabase / PostgreSQL + psycopg2 |
| Frontend | React 18 + Vite 5 |
| Maps | react-leaflet 4.2.1 + leaflet 1.9.4 |
| Routing | OSRM public API (no key needed), steps=true untuk nav panel |
| Geocoding | Nominatim / OpenStreetMap (search + reverse geocode) |
| Map tiles | Carto Dark Matter (dark) / Carto Positron (light) |
| i18n | Custom translations.js + AppContext (ID/EN) |
| Theme | CSS variables, `data-theme="light/dark"` on `<html>` |

---

## Struktur File Penting

```
D:\FloodAI - Copy\
├── api/
│   ├── main.py                    # FastAPI app, semua endpoint
│   └── routes/
│       ├── chat.py                # POST /api/chat (Groq SDK, max_tokens=1200)
│       └── agentic_llm.py        # POST /api/agentic-llm
├── services/
│   └── decision_engine.py        # Engine prediksi banjir
├── Dockerfile                     # python:3.12-slim, CMD uvicorn 0.0.0.0:8080
├── fly.toml                       # Fly.io config, internal_port=8080, region=sin
├── frontend/
│   ├── .npmrc                    # legacy-peer-deps=true
│   ├── package.json              # react-leaflet pinned ^4.2.1
│   ├── vercel.json               # root dir = frontend/, rewrites SPA
│   └── src/
│       ├── main.jsx              # entry — import 'leaflet/dist/leaflet.css'
│       ├── styles.css            # design system: dark + light theme, semua CSS
│       ├── App.jsx               # Provider (AppContext) + shell: topbar + nav 3 item
│       ├── pages/
│       │   ├── Home.jsx          # Command Center (operator BPBD)
│       │   ├── Alert.jsx         # Evacuation route planner (warga) + GPS
│       │   └── About.jsx         # Halaman tentang sistem + credit @juanvier_
│       ├── components/
│       │   ├── FloodMap.jsx      # Peta risiko Jakarta, maxBounds, theme-aware tiles
│       │   ├── EvacuationMap.jsx # Peta rute evakuasi + GPS blue dot + nav panel
│       │   ├── ChatBot.jsx       # Floating chatbot FAB 64px
│       │   ├── AlertBanner.jsx   # Ribbon alert, lang-aware
│       │   ├── EmergencyContacts.jsx  # i18n-aware
│       │   └── LoadingSpinner.jsx
│       ├── hooks/
│       │   ├── useFloodRisk.js   # fetch /predict/realtime-native, poll 15 menit
│       │   └── useChat.js        # chat state, pass lang ke floodAgent
│       └── lib/
│           ├── appContext.js     # AppContext (lang, theme), useApp(), useT()
│           ├── translations.js   # Semua string ID/EN, fungsi translate()
│           ├── floodAgent.js     # sendToFloodAgent → POST /api/chat, auto-lang
│           └── humanize.js       # humanizeRiskLevel(level, lang), humanizeRainfall
├── context.md                    # file ini
└── .env                          # JANGAN di-commit — GROQ_API_KEY dll
```

---

## API Endpoints Backend (Fly.io)

| Method | Path | Keterangan |
|---|---|---|
| GET | `/healthz` | Health check |
| GET | `/predict/realtime-native` | **Main** — risk level, probability, features |
| POST | `/api/chat` | Chat via Groq (no API key di frontend) |
| POST | `/predict/agentic` | Agentic pipeline (butuh API key header) |

### Response `/predict/realtime-native`
```json
{
  "risk_level": "SAFE|PRE_ALERT|WARNING|DANGER",
  "probability": 0.0–1.0,
  "risk_interpretation": "string",
  "features": { "rainfall_mm": 0.0, ... }
}
```

### Mapping level di frontend
```js
SAFE → "aman"  |  PRE_ALERT → "waspada"  |  WARNING → "siaga"  |  DANGER → "bahaya"
```

---

## Environment Variables

### Backend (Fly.io secrets)
```
GROQ_API_KEY=sk-...
GROQ_MODEL=llama-3.3-70b-versatile
DATABASE_URL=postgresql://...   # kalau pakai Supabase
```

Set via: `flyctl secrets set GROQ_API_KEY=xxx -a floodai`

### Frontend (Vercel)
```
VITE_API_BASE_URL=https://floodai.fly.dev
```

**Penting:** Setelah ubah env var di Vercel, harus redeploy manual atau push commit baru.

---

## Fitur Frontend yang Sudah Ada

### Navigasi (3 halaman)
- **Command Center** (`Home.jsx`) — dashboard operator BPBD
- **Evakuasi** (`Alert.jsx`) — route planner warga
- **Tentang / About** (`About.jsx`) — info sistem + credit @juanvier_

### Command Center (`Home.jsx`)
```
[Topbar: logo | nav 3 item | EN/ID toggle | ☀/🌙 toggle | SYSTEM ONLINE]
[AlertRibbon: muncul kalau siaga1/siaga2 > 0, lang-aware]
[4 MetricCards: Zona Siaga* | Warga Terdampak* | Skor Risiko● | Curah Hujan●]
  (* = est., ● = real data)
[cmd-main grid: 1fr + 320px, align-items:stretch]
  [Kiri .cmd-left: FloodMap flex:1 (maxBounds Jakarta, minZoom 10)]
  [Kanan: AlertPanel + AgentPanel(dinamis) + RecommendationsPanel]
[Model Output — full width, dari backend]
[ZoneTable — full width, 5 wilayah, OOD tag, prob bar, RiskBadge i18n]
[FloatingChatBot FAB 64px]
```

### Evakuasi (`Alert.jsx`)
```
[evac-grid: minmax(0,1fr) + 380px, align-items:stretch]
  [Kiri .evac-col-left:
    [Search panel: DARI label + text input + Cari btn + ⊕ GPS btn]
    [Autocomplete dropdown: Nominatim suggestions 6 item, debounce 400ms]
    [EvacuationMap: flex:1, maxBounds, minZoom 10]
      [Nav panel: arrow + street name + next turn — muncul saat route ada]
      [GPS blue dot: CircleMarker biru + pulse ring kalau origin.isGPS=true]
    [Legend dots]
  ]
  [Kanan: Status hero (humanizeRiskLevel lang-aware) + 5 Langkah + Contacts]
[FloatingChatBot]
```

**Fitur input lokasi (3 cara):**
1. Ketik alamat → autocomplete Nominatim → klik suggestion → langsung route
2. Klik tombol `⊕` → `navigator.geolocation.getCurrentPosition` → reverse geocode → route
3. Klik langsung di peta → reverse geocode koordinat → route

### ChatBot
- FAB 64px pojok kanan bawah
- Panel 360×500px, animasi pop-up
- System prompt: language rule PERTAMA, context prefix `[flood_risk: X | rainfall: Y mm/h]`
- Auto-detect bahasa dari pesan user → respond dalam bahasa sama (EN/ID)
- max_tokens: 1200

### Theme & Language
- **Dark/Light toggle** `☀/🌙` di topbar → `data-theme` on `<html>`, disimpan localStorage
- **EN/ID toggle** di topbar → AppContext, disimpan localStorage
- Light mode: tile Carto Positron, panel putih, shadows subtle
- Semua string di `translations.js`, akses via `useT()` hook

---

## i18n System

```js
// appContext.js
export const AppContext = createContext({ lang: "id", theme: "dark" });
export function useApp() { return useContext(AppContext); }
export function useT() {
  const { lang } = useContext(AppContext);
  return (key, vars) => translate(lang, key, vars);
}

// translations.js
export function translate(lang, key, vars = {}) { ... }
// Key contoh: "metric.riskScore", "evac.from", "step.1.t", "risk.SIAGA_1"
```

**humanize.js** sekarang lang-aware:
```js
humanizeRiskLevel("aman", "en") // → { label: "SAFE", color: "var(--safe)", desc: "No flood risk..." }
humanizeRiskLevel("bahaya", "id") // → { label: "BAHAYA", color: "var(--s1)", desc: "Evakuasi segera..." }
```

---

## Design System

### Dark Theme (default)
```css
--bg: #09090d       --panel: #111117     --panel-2: #16161e
--text: #edf0fb     --muted: #7a8299     --muted-2: #454d65
--cyan: #00cfff     --s1: #ff3d5a        --s2: #f97316
--wsp: #f5a623      --safe: #00e5a0
```

### Light Theme (`[data-theme="light"]`)
```css
--bg: #eef1f8       --panel: #ffffff     --panel-2: #f4f6fc
--text: #161929     --muted: #5a6480     --muted-2: #90a0be
--cyan: #0088bb     --s1: #d42040        --safe: #008a5e
```

Fonts: **Space Grotesk** (headings) · **JetBrains Mono** (labels, mono) · **Inter** (body)

---

## Data Zones (Derived)

Zone data di-derive dari `riskScore` backend dengan bias historis:

```js
const BASE_ZONES = [
  { zone: "Penjaringan", district: "Jakarta Utara", bias: +15, tma_base: 900 },
  { zone: "Cengkareng",  district: "Jakarta Barat",  bias: +8,  tma_base: 820 },
  { zone: "Jatinegara",  district: "Jakarta Timur",  bias: +2,  tma_base: 750, is_ood: true },
  { zone: "Kalideres",   district: "Jakarta Barat",  bias: -8,  tma_base: 640 },
  { zone: "Kebayoran",   district: "Jakarta Selatan", bias: -22, tma_base: 340 },
];
```

Metric card labels: `● real` (Skor Risiko, Curah Hujan) vs `○ est.` (Zona Siaga, Warga Terdampak).

---

## Shelter Destinations (EvacuationMap)

```js
DESTINATIONS = [
  { id: "kemayoran", name: "Kemayoran (Shelter)",   lat: -6.1528, lng: 106.8559 },
  { id: "ancol",     name: "Ancol (Pos Evakuasi)",  lat: -6.1246, lng: 106.8350 },
  { id: "tmii",      name: "TMII (Pos Darurat)",    lat: -6.2726, lng: 106.9020 },
  { id: "gbk",       name: "GBK Senayan (Shelter)", lat: -6.2181, lng: 106.8022 },
  { id: "cipete",    name: "Cipete (Pos Aman)",     lat: -6.2824, lng: 106.8043 },
]
```

`findNearestShelter(lat, lng)` — Haversine distance, export dari EvacuationMap.jsx

---

## Known Issues / Catatan Teknis

| Issue | Status | Catatan |
|---|---|---|
| TMA scraper broken | Backend — offline | rainfall_mm = 0 dari backend, bukan display bug |
| ECE kalibrasi 0.38 | Model confidence belum penuh | Ditampilkan di footer & About page |
| Zone data is mock-derived | Derived dari riskScore + bias | Dilabeli "○ est." di metric cards |
| BNPB district mapping gap | Kecamatan write-back belum lengkap | — |
| Fly.io tidak listen | Jika GROQ_API_KEY tidak di-set | Uvicorn crash sebelum bind port |

---

## Vercel Build Config

```json
{
  "installCommand": "npm install --legacy-peer-deps",
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

**Penting:** Vercel Root Directory = `frontend/`. Semua path relatif terhadap `frontend/`. Jangan tambah `cd frontend &&`.

---

## react-leaflet Version Lock

```
react-leaflet@4.2.1  ← JANGAN upgrade ke ^5.x (butuh React 19)
```

Leaflet CSS wajib import dari npm (bukan CDN):
```js
// main.jsx — harus SEBELUM styles.css
import "leaflet/dist/leaflet.css";
```

---

## Cara Jalankan Lokal

```bash
# Backend
cd "D:\FloodAI - Copy"
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
# Butuh: GROQ_API_KEY di .env

# Frontend
cd "D:\FloodAI - Copy\frontend"
npm run dev
# Buka http://localhost:5173
# Buat file .env.local: VITE_API_BASE_URL=http://localhost:8080
```

---

## Semua yang Sudah Dikerjakan (Kronologis)

1. **`/api/chat` endpoint** — Groq SDK, `api/routes/chat.py`, max_tokens naik 512→1200
2. **Redesign frontend** — basic → dark operator dashboard
3. **Leaflet maps** — FloodMap (risiko per wilayah) + EvacuationMap (OSRM routing)
4. **Command Center layout** — 4 metric cards + map + sidebar + zone table
5. **Floating ChatBot** — FAB 64px, panel 360×500, Groq backend
6. **Address input + geocoding** — Nominatim search, autocomplete dropdown, Haversine nearest shelter
7. **Language enrichment chatbot** — system prompt kaya, max_tokens 1200
8. **Rainfall data fix** — pass dari useFloodRisk → App → Alert → ChatBot
9. **Chatbot anti-hallucination** — larang prediksi cuaca, arahkan ke BMKG
10. **Layout overhaul** — evac-grid stretch, cmd-left flex, hilangkan gap hitam
11. **Legend overlay** — FloodMap internal CSS legend `.map-legend`
12. **Data honesty labels** — `● real` vs `○ est.` di metric cards
13. **Dynamic agent statuses** — berdasarkan level risiko aktual, label "simulasi"
14. **Shelter Terisi** → diganti **Curah Hujan** (data real dari sensor)
15. **Dark/Light theme** — CSS vars `[data-theme]`, tile Carto switch, localStorage
16. **EN/ID language toggle** — `translations.js`, `AppContext`, `useT()` hook
17. **Map bounds lock** — Jakarta `maxBounds` + `minZoom:10` di kedua peta
18. **humanize.js lang-aware** — AMAN→SAFE, WASPADA→WARNING, dll
19. **Chatbot auto-detect language** — context prefix English-neutral, language rule baris pertama
20. **RiskBadge + AlertRibbon** — sekarang i18n via `t()`, tidak lagi hardcoded
21. **About page** — data sources, model ML, tech stack, disclaimer, credit @juanvier_ + IG button
22. **GPS location tracking** — tombol ⊕, `navigator.geolocation`, blue dot + pulse ring
23. **Map click to set location** — `useMapEvents`, reverse geocode → auto-fill input
24. **OSRM nav panel** — fetch dengan `steps=true`, tampilkan arrow + street name + next turn
25. **Mobile responsive** — breakpoints 1100/900/640/420px, compact topbar, chatbot full-width
26. **Navbar lebih besar** — font 0.82rem, padding lebih besar
27. **FAB lebih besar** — 52→64px, shadow lebih prominent
28. **Light mode chat fix** — input/bubble warna benar di light mode
