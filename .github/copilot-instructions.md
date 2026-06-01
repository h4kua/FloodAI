# GitHub Copilot Instructions
# Project: FloodAI — Frontend (Vite + React)
# Deployment: Vercel
# Letakkan di: .github/copilot-instructions.md

---

## IDENTITAS PROJECT

FloodAI adalah sistem peringatan banjir berbasis AI untuk masyarakat Indonesia.
Frontend dibangun dengan Vite + React, dideploy di Vercel.
Target pengguna: masyarakat umum, relawan, BPBD — bukan developer.

Stack:
- Frontend: Vite + React + Tailwind CSS
- AI Agent: Anthropic Claude API (via proxy backend atau Vercel Edge Function)
- Deployment: Vercel (Vite framework preset)
- Map: Leaflet.js atau Mapbox GL

---

## BAGIAN 1 — FIX VERCEL DEPLOYMENT (VITE)

### Konfigurasi wajib di Vercel Dashboard:
```
Framework Preset  : Vite
Build Command     : vite build
Output Directory  : dist
Install Command   : npm install
Node.js Version   : 18.x
```

### `vite.config.js` yang benar untuk Vercel:
```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
        }
      }
    }
  },
  server: {
    port: 3000,
  }
})
```

### `vercel.json` wajib ada di root project:
```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ],
  "buildCommand": "vite build",
  "outputDirectory": "dist",
  "framework": "vite"
}
```

### `package.json` scripts yang benar:
```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "lint": "eslint . --ext js,jsx --report-unused-disable-directives"
  }
}
```

### `.env` setup untuk Vite:
```env
# .env.local — jangan di-commit ke GitHub
VITE_API_URL=https://your-backend.railway.app
VITE_ANTHROPIC_API_KEY=your_key_here
VITE_MAPBOX_TOKEN=your_mapbox_token
```
Di Vercel Dashboard → Settings → Environment Variables → tambahkan semua VITE_ prefix.

⚠️ PENTING: Vite hanya expose env variable yang diawali `VITE_`.
Contoh benar: `import.meta.env.VITE_API_URL`
Contoh salah: `process.env.API_URL` ← ini tidak akan terbaca di Vite

### Penyebab build gagal yang paling umum di Vite + Vercel:

#### 1. Import path salah (case-sensitive di Linux)
```javascript
// SALAH — Windows tidak masalah, tapi Vercel (Linux) crash
import Header from './components/header'

// BENAR
import Header from './components/Header'
```

#### 2. Package belum diinstall tapi diimport
```bash
# Cek dulu di lokal
npm run build
# Kalau error di lokal → pasti error di Vercel juga
```

#### 3. Environment variable tidak pakai `import.meta.env`
```javascript
// SALAH
const apiUrl = process.env.VITE_API_URL

// BENAR
const apiUrl = import.meta.env.VITE_API_URL
```

#### 4. React tidak diimport di file JSX (Vite tidak auto-import)
```javascript
// Tambahkan di atas setiap file JSX jika pakai React < 17
import React from 'react'
```

---

## BAGIAN 2 — STRUKTUR FOLDER PROJECT

```
floodai-frontend/
├── public/
│   └── favicon.ico
├── src/
│   ├── components/
│   │   ├── AlertBanner.jsx       ← status banjir di atas semua halaman
│   │   ├── RiskCard.jsx          ← card level risiko
│   │   ├── FloodChatbot.jsx      ← chat dengan AI agent
│   │   ├── EmergencyContacts.jsx ← nomor darurat
│   │   ├── EvacuationSteps.jsx   ← langkah evakuasi
│   │   ├── FloodMap.jsx          ← peta interaktif
│   │   └── LoadingSpinner.jsx    ← loading state
│   ├── pages/
│   │   ├── Home.jsx              ← dashboard utama
│   │   ├── Alert.jsx             ← halaman peringatan
│   │   ├── Chat.jsx              ← chat dengan FloodAI
│   │   ├── Map.jsx               ← peta risiko
│   │   └── Info.jsx              ← panduan & edukasi
│   ├── lib/
│   │   ├── floodAgent.js         ← Claude API calls
│   │   ├── humanize.js           ← terjemah data teknis → awam
│   │   └── riskAnalysis.js       ← analisis risiko otomatis
│   ├── hooks/
│   │   ├── useFloodRisk.js       ← hook polling data risiko
│   │   └── useChat.js            ← hook untuk chat agent
│   ├── App.jsx
│   ├── main.jsx
│   └── index.css
├── .env.local
├── .gitignore
├── vercel.json
├── vite.config.js
└── package.json
```

---

## BAGIAN 3 — FRONTEND USER-FRIENDLY UNTUK MASYARAKAT

### Prinsip desain wajib:
- Semua teks UI dalam Bahasa Indonesia yang sederhana
- Warna intuitif: HIJAU = aman, KUNING = waspada, MERAH = bahaya
- Setiap icon HARUS disertai teks (jangan icon saja)
- Font minimal 16px untuk body, 20px untuk heading penting
- Mobile-first — mayoritas pengguna pakai HP
- Tombol darurat selalu terlihat di setiap halaman
- Loading state wajib ada dengan teks yang jelas

### Tema warna & font (di `index.css`):
```css
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&family=DM+Sans:wght@400;500&display=swap');

:root {
  --color-safe:     #22c55e;
  --color-warning:  #f59e0b;
  --color-danger:   #ef4444;
  --color-critical: #7f1d1d;
  --color-bg:       #0f172a;
  --color-surface:  #1e293b;
  --color-border:   #334155;
  --color-text:     #f1f5f9;
  --color-muted:    #94a3b8;
  --font-display:   'Plus Jakarta Sans', sans-serif;
  --font-body:      'DM Sans', sans-serif;
}

body {
  background-color: var(--color-bg);
  color: var(--color-text);
  font-family: var(--font-body);
  font-size: 16px;
}
```

### `AlertBanner.jsx` — Banner status di atas semua halaman:
```jsx
const levelConfig = {
  aman:    { bg: 'bg-green-500',  icon: '🟢', text: 'AMAN — Tidak ada risiko banjir saat ini' },
  waspada: { bg: 'bg-yellow-500', icon: '🟡', text: 'WASPADA — Pantau kondisi cuaca' },
  siaga:   { bg: 'bg-orange-500', icon: '🟠', text: 'SIAGA — Bersiap untuk evakuasi' },
  bahaya:  { bg: 'bg-red-600',    icon: '🔴', text: 'BAHAYA — Segera lakukan evakuasi!' },
};

export default function AlertBanner({ level = 'waspada' }) {
  const config = levelConfig[level] || levelConfig.waspada;
  return (
    <div className={`${config.bg} text-white text-center py-3 px-4 font-bold text-lg`}>
      {config.icon} {config.text}
    </div>
  );
}
```

### `RiskCard.jsx` — Card level risiko yang mudah dipahami:
```jsx
export default function RiskCard({ riskData }) {
  const { level, waterLevel, rainfall, estimatedTime } = riskData;
  return (
    <div className="bg-slate-800 rounded-2xl p-6 space-y-4">
      <h2 className="text-xl font-bold">📊 Status Wilayah Anda</h2>
      <div className="grid grid-cols-2 gap-4">
        <StatItem icon="💧" label="Ketinggian Air" value={humanizeWaterLevel(waterLevel)} />
        <StatItem icon="🌧️" label="Intensitas Hujan" value={humanizeRainfall(rainfall)} />
        <StatItem icon="⏱️" label="Estimasi Puncak" value={estimatedTime || 'Sedang dihitung'} />
        <StatItem icon="📍" label="Level Risiko" value={humanizeRiskLevel(level).label} />
      </div>
    </div>
  );
}

function StatItem({ icon, label, value }) {
  return (
    <div className="bg-slate-700 rounded-xl p-3">
      <p className="text-slate-400 text-sm">{icon} {label}</p>
      <p className="text-white font-semibold mt-1">{value}</p>
    </div>
  );
}
```

### `EvacuationSteps.jsx` — Panduan evakuasi step-by-step:
```jsx
const steps = [
  { step: 1, icon: '📦', title: 'Siapkan Tas Darurat', desc: 'Dokumen penting, obat-obatan, pakaian 3 hari, air minum' },
  { step: 2, icon: '🔌', title: 'Matikan Listrik & Gas', desc: 'Cabut semua peralatan listrik dan matikan kompor gas' },
  { step: 3, icon: '📞', title: 'Hubungi Keluarga', desc: 'Beritahu anggota keluarga tentang rencana evakuasi' },
  { step: 4, icon: '🚶', title: 'Pergi ke Titik Kumpul', desc: 'Menuju lokasi pengungsian terdekat yang aman' },
  { step: 5, icon: '📋', title: 'Daftar di Posko', desc: 'Laporkan diri ke petugas di tempat pengungsian' },
];

export default function EvacuationSteps() {
  return (
    <div className="space-y-3">
      <h2 className="text-xl font-bold">🚨 Langkah Evakuasi</h2>
      {steps.map(s => (
        <div key={s.step} className="flex items-start gap-4 bg-slate-800 rounded-xl p-4">
          <span className="text-3xl">{s.icon}</span>
          <div>
            <p className="font-bold">{s.step}. {s.title}</p>
            <p className="text-slate-400 text-sm mt-1">{s.desc}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
```

### `EmergencyContacts.jsx` — Selalu tampil di semua halaman:
```jsx
const contacts = [
  { name: 'BPBD Nasional', number: '117', icon: '🏛️' },
  { name: 'Basarnas',       number: '115', icon: '🚁' },
  { name: 'Ambulans',       number: '118', icon: '🚑' },
  { name: 'Pemadam',        number: '113', icon: '🚒' },
  { name: 'Polisi',         number: '110', icon: '🚔' },
];

export default function EmergencyContacts() {
  return (
    <div className="bg-red-950 border border-red-700 rounded-2xl p-4">
      <h3 className="font-bold text-red-400 mb-3">📞 Nomor Darurat</h3>
      <div className="grid grid-cols-2 gap-2">
        {contacts.map(c => (
          <a key={c.name} href={`tel:${c.number}`}
            className="flex items-center gap-2 bg-red-900 rounded-xl p-3 hover:bg-red-800 transition">
            <span className="text-xl">{c.icon}</span>
            <div>
              <p className="text-xs text-red-300">{c.name}</p>
              <p className="font-bold text-white">{c.number}</p>
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}
```

---

## BAGIAN 4 — AGENTIC AI (CLAUDE API)

### `lib/floodAgent.js` — Chat Agent utama:
```javascript
const SYSTEM_PROMPT = `
Kamu adalah FloodAI, asisten AI untuk sistem peringatan banjir Indonesia.
Bantu masyarakat memahami risiko banjir dan tindakan yang harus diambil.

ATURAN:
- Selalu gunakan Bahasa Indonesia yang sederhana dan mudah dipahami
- Tenang dan empatis, tidak menimbulkan kepanikan berlebihan
- Berikan langkah konkret yang bisa langsung dilakukan
- Jika situasi darurat, selalu sarankan hubungi BPBD (117) atau Basarnas (115)
- Jangan gunakan istilah teknis tanpa penjelasan
`;

export async function sendToFloodAgent(message, history = [], riskContext = {}) {
  const contextMessage = riskContext.level
    ? `[Konteks: Level risiko saat ini ${riskContext.level}, curah hujan ${riskContext.rainfall || 'tidak diketahui'} mm/jam]`
    : '';

  try {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1000,
        system: SYSTEM_PROMPT,
        messages: [
          ...history,
          { role: 'user', content: contextMessage ? `${contextMessage}\n${message}` : message }
        ]
      })
    });

    const data = await response.json();
    return {
      success: true,
      reply: data.content[0].text,
      timestamp: new Date().toISOString()
    };
  } catch (error) {
    return {
      success: false,
      reply: 'Maaf, asisten AI sedang tidak tersedia. Untuk darurat, hubungi BPBD di nomor 117.',
      timestamp: new Date().toISOString()
    };
  }
}
```

### `lib/riskAnalysis.js` — Analisis risiko otomatis:
```javascript
export async function analyzeRisk(weatherData, sensorData) {
  try {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 500,
        messages: [{
          role: 'user',
          content: `Analisis risiko banjir. Kembalikan HANYA JSON tanpa teks lain.
Data: ${JSON.stringify({ weatherData, sensorData })}
Format: {"risk_level":"aman|waspada|siaga|bahaya","risk_score":0-100,"alert_message":"pesan bahasa Indonesia","evacuation_needed":true/false,"estimated_peak":"estimasi waktu"}`
        }]
      })
    });

    const data = await response.json();
    const text = data.content[0].text.replace(/```json|```/g, '').trim();
    return JSON.parse(text);
  } catch {
    return { risk_level: 'waspada', risk_score: 50, error: true };
  }
}
```

### `hooks/useFloodRisk.js` — Polling otomatis tiap 15 menit:
```javascript
import { useState, useEffect } from 'react';
import { analyzeRisk } from '../lib/riskAnalysis';

export function useFloodRisk(location) {
  const [riskData, setRiskData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);

  const fetchRisk = async () => {
    try {
      // Ganti dengan API cuaca/sensor real
      const weatherData = { rainfall: 35, humidity: 90 };
      const sensorData  = { waterLevel: 120, location };
      const result = await analyzeRisk(weatherData, sensorData);
      setRiskData(result);
      setLastUpdated(new Date());
    } catch (err) {
      console.error('Risk fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRisk();
    const interval = setInterval(fetchRisk, 15 * 60 * 1000); // tiap 15 menit
    return () => clearInterval(interval);
  }, [location]);

  return { riskData, loading, lastUpdated, refresh: fetchRisk };
}
```

### `hooks/useChat.js` — State management chat:
```javascript
import { useState } from 'react';
import { sendToFloodAgent } from '../lib/floodAgent';

export function useChat(riskContext) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Halo! Saya FloodAI 🌊 Saya siap membantu Anda dengan informasi dan panduan terkait banjir. Ada yang bisa saya bantu?'
    }
  ]);
  const [loading, setLoading] = useState(false);

  const sendMessage = async (text) => {
    const userMsg = { role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    const history = messages.map(m => ({ role: m.role, content: m.content }));
    const result = await sendToFloodAgent(text, history, riskContext);

    setMessages(prev => [...prev, { role: 'assistant', content: result.reply }]);
    setLoading(false);
  };

  return { messages, loading, sendMessage };
}
```

---

## BAGIAN 5 — TERJEMAH DATA TEKNIS → AWAM

### `lib/humanize.js`:
```javascript
export function humanizeRiskLevel(level) {
  const map = {
    aman:    { label: 'AMAN',    color: '#22c55e', bg: 'bg-green-500',  desc: 'Tidak ada risiko banjir saat ini' },
    waspada: { label: 'WASPADA', color: '#f59e0b', bg: 'bg-yellow-500', desc: 'Pantau kondisi cuaca secara berkala' },
    siaga:   { label: 'SIAGA',   color: '#f97316', bg: 'bg-orange-500', desc: 'Bersiap untuk evakuasi jika diperlukan' },
    bahaya:  { label: 'BAHAYA',  color: '#ef4444', bg: 'bg-red-600',    desc: 'Segera lakukan evakuasi ke tempat aman' },
  };
  return map[level] || map.waspada;
}

export function humanizeWaterLevel(cm) {
  if (!cm) return 'Data tidak tersedia';
  if (cm < 30)  return `${cm} cm — Sangat rendah`;
  if (cm < 60)  return `${cm} cm — Setinggi lutut anak`;
  if (cm < 100) return `${cm} cm — Setinggi lutut orang dewasa`;
  if (cm < 150) return `${cm} cm — Setinggi pinggang orang dewasa`;
  if (cm < 200) return `${cm} cm — Setinggi dada orang dewasa`;
  return `${cm} cm — Di atas kepala — ⚠️ SANGAT BERBAHAYA`;
}

export function humanizeRainfall(mmPerHour) {
  if (!mmPerHour) return 'Tidak ada hujan';
  if (mmPerHour < 5)   return 'Gerimis ringan';
  if (mmPerHour < 20)  return 'Hujan sedang';
  if (mmPerHour < 50)  return 'Hujan lebat';
  if (mmPerHour < 100) return 'Hujan sangat lebat ⚠️';
  return 'Hujan ekstrem — Potensi banjir bandang 🚨';
}

export function humanizeTime(isoString) {
  if (!isoString) return 'Belum diketahui';
  const date = new Date(isoString);
  return date.toLocaleString('id-ID', {
    weekday: 'long', hour: '2-digit', minute: '2-digit'
  });
}
```

---

## BAGIAN 6 — QUICK REPLY CHATBOT

```javascript
// Pertanyaan siap pakai untuk user di halaman chat
export const quickReplies = [
  { icon: '🏠', text: 'Apakah rumah saya aman dari banjir?' },
  { icon: '🚶', text: 'Ke mana saya harus mengungsi?' },
  { icon: '📦', text: 'Apa yang harus dibawa saat evakuasi?' },
  { icon: '📞', text: 'Siapa yang harus dihubungi saat banjir?' },
  { icon: '⚠️', text: 'Apa tanda-tanda banjir akan datang?' },
  { icon: '👨‍👩‍👧', text: 'Bagaimana melindungi anak-anak saat banjir?' },
  { icon: '💊', text: 'Obat apa yang harus dibawa saat mengungsi?' },
  { icon: '🔌', text: 'Apa yang harus dimatikan sebelum mengungsi?' },
];
```

---

## BAGIAN 7 — ATURAN COPILOT WAJIB

### Deployment & Build:
- SELALU gunakan `import.meta.env.VITE_` bukan `process.env`
- SELALU pastikan `vercel.json` ada dengan rewrite rules
- SELALU cek nama file case-sensitive (Linux di Vercel)
- SELALU jalankan `npm run build` lokal sebelum push

### UI & UX:
- Semua teks UI dalam Bahasa Indonesia
- JANGAN tampilkan angka mentah — selalu pakai fungsi `humanize`
- JANGAN tampilkan istilah teknis: "API", "null", "error 500", "undefined"
- SELALU ada loading state dengan teks: "Sedang memuat data..."
- SELALU ada error state dengan teks: "Gagal memuat. Coba lagi."
- SELALU ada tombol kontak darurat di setiap halaman
- Semua tombol ukuran minimal 44x44px (standar mobile touch)

### AI & Data:
- SELALU wrap Claude API call dengan try/catch
- SELALU parse JSON response dengan aman (strip backtick dulu)
- SELALU ada fallback jika Claude API tidak tersedia
- Polling data risiko: setiap 15 menit dengan `setInterval`
- History chat tersimpan di `useState`, bukan localStorage
- JANGAN expose `VITE_ANTHROPIC_API_KEY` langsung di frontend production
  → Gunakan backend proxy atau Vercel Edge Function sebagai perantara
