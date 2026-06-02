import { useState } from "react";
import { humanizeRiskLevel } from "../lib/humanize";
import EvacuationMap, { DESTINATIONS, findNearestShelter } from "../components/EvacuationMap";
import EmergencyContacts from "../components/EmergencyContacts";
import ChatBot from "../components/ChatBot";

const STEPS = [
  { title: "Siapkan Tas Darurat",       desc: "Dokumen penting, obat, pakaian 3 hari, air minum, senter, power bank." },
  { title: "Matikan Listrik & Gas",     desc: "Cabut semua peralatan listrik dan tutup katup gas sebelum keluar." },
  { title: "Beritahu Seluruh Keluarga", desc: "Pastikan semua anggota tahu rencana evakuasi dan titik kumpul." },
  { title: "Ikuti Rute di Peta",        desc: "Gunakan rute yang ditampilkan. Hindari genangan dan jalan terputus." },
  { title: "Daftar di Pos Pengungsian", desc: "Laporkan diri ke petugas BPBD untuk pendataan dan bantuan." },
];

async function geocodeAddress(address) {
  const q = encodeURIComponent(address + ", Jakarta, Indonesia");
  const url = `https://nominatim.openstreetmap.org/search?q=${q}&format=json&limit=1&countrycodes=id`;
  const res = await fetch(url, {
    headers: { "Accept-Language": "id", "User-Agent": "deFlood.ai/1.0" },
  });
  if (!res.ok) throw new Error("Geocoding gagal");
  const data = await res.json();
  if (!data.length) throw new Error("Alamat tidak ditemukan");
  return {
    lat: parseFloat(data[0].lat),
    lng: parseFloat(data[0].lon),
    displayName: data[0].display_name,
  };
}

export default function Alert({ riskLevel = "waspada", rainfall = 0 }) {
  const [addressInput, setAddressInput] = useState("");
  const [userLocation, setUserLocation]  = useState(null);
  const [destId, setDestId]              = useState(null);
  const [geocoding, setGeocoding]        = useState(false);
  const [geoError, setGeoError]          = useState("");

  const config = humanizeRiskLevel(riskLevel);

  const selectedDest = destId
    ? DESTINATIONS.find((d) => d.id === destId) ?? null
    : null;

  const handleGeocode = async () => {
    const addr = addressInput.trim();
    if (!addr) return;
    setGeocoding(true);
    setGeoError("");
    setUserLocation(null);
    setDestId(null);
    try {
      const loc = await geocodeAddress(addr);
      const nearest = findNearestShelter(loc.lat, loc.lng);
      setUserLocation({ lat: loc.lat, lng: loc.lng, name: addr });
      setDestId(nearest.id);
    } catch (e) {
      setGeoError(e.message ?? "Alamat tidak ditemukan. Coba tambahkan nama kelurahan atau kecamatan.");
    } finally {
      setGeocoding(false);
    }
  };

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
            {/* Address input + geocode */}
            <div className="route-controls">
              <span className="route-label from">DARI</span>
              <input
                className="route-input"
                type="text"
                placeholder="Ketik alamat Anda di Jakarta..."
                value={addressInput}
                onChange={(e) => setAddressInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !geocoding && handleGeocode()}
                disabled={geocoding}
              />
              <button
                className="route-search-btn"
                onClick={handleGeocode}
                disabled={geocoding || !addressInput.trim()}
              >
                {geocoding ? "..." : "Cari"}
              </button>

              {/* Shelter result */}
              {userLocation && selectedDest && (
                <>
                  <span style={{ color: "var(--muted)", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.75rem" }}>→</span>
                  <span className="route-label to">SHELTER</span>
                  <select
                    className="route-select"
                    value={destId}
                    onChange={(e) => setDestId(e.target.value)}
                  >
                    {DESTINATIONS.map((d) => (
                      <option key={d.id} value={d.id}>{d.name}</option>
                    ))}
                  </select>
                </>
              )}
            </div>

            {/* Geocode error */}
            {geoError && (
              <div style={{
                position: "absolute", top: 72, left: 12, right: 12, zIndex: 1001,
                background: "rgba(255,61,90,0.12)", border: "1px solid rgba(255,61,90,0.3)",
                borderRadius: 10, padding: "0.5rem 0.875rem",
                fontFamily: "'JetBrains Mono',monospace", fontSize: "0.7rem", color: "#ff9dac",
              }}>
                {geoError}
              </div>
            )}

            <EvacuationMap origin={userLocation} dest={selectedDest} />
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

      <ChatBot riskContext={{ level: riskLevel, rainfall }} />
    </>
  );
}
