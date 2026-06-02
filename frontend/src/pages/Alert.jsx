import { useState } from "react";
import { humanizeRiskLevel } from "../lib/humanize";
import EvacuationMap, { ORIGINS, DESTINATIONS } from "../components/EvacuationMap";
import EmergencyContacts from "../components/EmergencyContacts";
import ChatBot from "../components/ChatBot";

const STEPS = [
  { title: "Siapkan Tas Darurat",       desc: "Dokumen penting, obat, pakaian 3 hari, air minum, senter, power bank." },
  { title: "Matikan Listrik & Gas",     desc: "Cabut semua peralatan listrik dan tutup katup gas sebelum keluar." },
  { title: "Beritahu Seluruh Keluarga", desc: "Pastikan semua anggota tahu rencana evakuasi dan titik kumpul." },
  { title: "Ikuti Rute di Peta",        desc: "Gunakan rute yang ditampilkan. Hindari genangan dan jalan terputus." },
  { title: "Daftar di Pos Pengungsian", desc: "Laporkan diri ke petugas BPBD untuk pendataan dan bantuan." },
];

export default function Alert({ riskLevel = "waspada" }) {
  const [originId, setOriginId] = useState("barat");
  const [destId,   setDestId]   = useState("kemayoran");
  const config = humanizeRiskLevel(riskLevel);

  return (
    <>
      {/* Page header */}
      <div className="page-header fade-in">
        <div>
          <p className="page-eyebrow">// Evacuation · Route Planner · Warga Jakarta</p>
          <h1 className="page-title">Rute Evakuasi</h1>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.4rem 0.875rem", borderRadius: "999px", border: `1px solid ${config.color}33`, background: `${config.color}0d` }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: config.color, animation: "blink 1.2s infinite", flexShrink: 0 }} />
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.7rem", fontWeight: 700, color: config.color, letterSpacing: "0.1em" }}>
            {config.label}
          </span>
        </div>
      </div>

      <div className="evac-grid fade-in">
        {/* Left: map */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          <div className="panel evac-map-panel" style={{ position: "relative" }}>
            {/* Route controls */}
            <div className="route-controls">
              <span className="route-label from">DARI</span>
              <select className="route-select" value={originId} onChange={(e) => setOriginId(e.target.value)}>
                {ORIGINS.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </select>
              <span style={{ color: "var(--muted-2)", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.75rem" }}>→</span>
              <span className="route-label to">KE</span>
              <select className="route-select" value={destId} onChange={(e) => setDestId(e.target.value)}>
                {DESTINATIONS.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </div>
            <EvacuationMap originId={originId} destId={destId} />
          </div>

          {/* Map legend */}
          <div style={{ display: "flex", gap: "1.5rem", padding: "0.25rem 0" }}>
            {[["#ff3d5a","Titik berangkat"],["#00cfff","Rute evakuasi"],["#00e5a0","Shelter aman"]].map(([c, l]) => (
              <div key={l} style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: c, boxShadow: `0 0 6px ${c}88`, flexShrink: 0 }} />
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", color: "var(--muted-2)" }}>{l}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right: steps + contacts */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          {/* Alert level hero */}
          <div className="panel panel-body" style={{ background: `linear-gradient(160deg,${config.color}0d,${config.color}06)`, border: `1px solid ${config.color}22`, textAlign: "center" }}>
            <p style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.66rem", color: config.color, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: "0.5rem" }}>Status Aktif</p>
            <p style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: "2.25rem", fontWeight: 800, letterSpacing: "-0.03em", color: config.color, lineHeight: 1, marginBottom: "0.5rem" }}>
              {config.label}
            </p>
            <p style={{ fontSize: "0.83rem", color: "var(--muted)", lineHeight: 1.5 }}>{config.desc}</p>
          </div>

          {/* Steps */}
          <div className="panel panel-body">
            <p className="panel-title">Langkah Evakuasi</p>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {STEPS.map((s, i) => (
                <div key={i} className="step">
                  <span className="step-num">{i + 1}</span>
                  <div>
                    <p className="step-title">{s.title}</p>
                    <p className="step-desc">{s.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <EmergencyContacts />
        </div>
      </div>

      <ChatBot riskContext={{ level: riskLevel }} />
    </>
  );
}
