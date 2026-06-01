import { useState } from "react";
import { humanizeRiskLevel } from "../lib/humanize";
import EvacuationMap, { ORIGINS, DESTINATIONS } from "../components/EvacuationMap";
import EmergencyContacts from "../components/EmergencyContacts";

const STEPS = [
  { title: "Siapkan Tas Darurat",       desc: "Dokumen penting, obat, pakaian 3 hari, air minum, senter, power bank." },
  { title: "Matikan Listrik & Gas",     desc: "Cabut semua peralatan listrik dan tutup katup gas sebelum keluar." },
  { title: "Beritahu Keluarga",         desc: "Pastikan semua anggota keluarga tahu rencana evakuasi dan titik kumpul." },
  { title: "Ikuti Rute Peta",           desc: "Gunakan rute di peta ini. Hindari area genangan. Jangan lewati air mengalir deras." },
  { title: "Daftar di Pos Pengungsian", desc: "Laporkan diri ke petugas BPBD untuk pendataan dan mendapat bantuan." },
];

export default function Alert({ riskLevel = "waspada" }) {
  const [originId, setOriginId] = useState("barat");
  const [destId,   setDestId]   = useState("kemayoran");
  const config = humanizeRiskLevel(riskLevel);

  return (
    <>
      <div className="page-bar fade-up">
        <div>
          <p className="page-eyebrow">// Evacuation / Route Planner</p>
          <h2 className="page-title">Rute Evakuasi</h2>
        </div>
        <div style={{
          display: "flex", alignItems: "center", gap: "0.5rem",
          padding: "0.5rem 0.875rem", borderRadius: "999px",
          border: `1px solid ${config.color}44`,
          background: `${config.color}11`,
        }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: config.color, flexShrink: 0 }} />
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.72rem", fontWeight: 700, color: config.color, letterSpacing: "0.1em" }}>
            {config.label}
          </span>
        </div>
      </div>

      <div className="evac-grid fade-up">
        {/* Left: map */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <div className="evac-map-panel">
            {/* Route controls overlay */}
            <div className="route-controls">
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flex: 1, flexWrap: "wrap" }}>
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.68rem", color: "#ff9dac", letterSpacing: "0.08em", flexShrink: 0 }}>DARI</span>
                <select
                  className="route-select"
                  value={originId}
                  onChange={(e) => setOriginId(e.target.value)}
                >
                  {ORIGINS.map((o) => (
                    <option key={o.id} value={o.id}>{o.name}</option>
                  ))}
                </select>

                <span className="route-arrow-label">→</span>

                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.68rem", color: "#8cffd8", letterSpacing: "0.08em", flexShrink: 0 }}>KE</span>
                <select
                  className="route-select"
                  value={destId}
                  onChange={(e) => setDestId(e.target.value)}
                >
                  {DESTINATIONS.map((d) => (
                    <option key={d.id} value={d.id}>{d.name}</option>
                  ))}
                </select>
              </div>
            </div>

            <EvacuationMap originId={originId} destId={destId} />
          </div>

          {/* Map legend */}
          <div style={{ display: "flex", gap: "1.25rem", padding: "0.5rem 0.25rem" }}>
            {[
              { color: "#ff3d5a", label: "Titik berangkat" },
              { color: "#00cfff", label: "Rute evakuasi" },
              { color: "#00e5a0", label: "Titik aman / shelter" },
            ].map((r) => (
              <div key={r.label} style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: r.color, flexShrink: 0, boxShadow: `0 0 6px ${r.color}88` }} />
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.68rem", color: "var(--muted-2)" }}>{r.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right: steps + contacts */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          {/* Alert level */}
          <div className="panel" style={{
            background: `linear-gradient(180deg,${config.color}11,${config.color}07)`,
            border: `1px solid ${config.color}33`,
            textAlign: "center",
          }}>
            <p style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.68rem", color: config.color, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: "0.5rem" }}>
              Status Aktif
            </p>
            <p style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: "2rem", fontWeight: 800, letterSpacing: "-0.03em", color: config.color, marginBottom: "0.375rem" }}>
              {config.label}
            </p>
            <p style={{ fontSize: "0.85rem", color: "var(--muted)", lineHeight: 1.5 }}>
              {config.desc}
            </p>
          </div>

          {/* Steps */}
          <div className="panel">
            <p className="sect-label" style={{ marginTop: 0 }}>Langkah Evakuasi</p>
            <div className="steps">
              {STEPS.map((step, i) => (
                <div key={i} className="step">
                  <span className="step-num">{i + 1}</span>
                  <div>
                    <p className="step-title">{step.title}</p>
                    <p className="step-desc">{step.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <EmergencyContacts />
        </div>
      </div>
    </>
  );
}
