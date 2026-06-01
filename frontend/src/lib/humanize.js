export function humanizeRiskLevel(level) {
  const map = {
    aman:    { label: "AMAN",    emoji: "🟢", color: "#22c55e", desc: "Tidak ada risiko banjir saat ini" },
    waspada: { label: "WASPADA", emoji: "🟡", color: "#f59e0b", desc: "Pantau kondisi cuaca secara berkala" },
    siaga:   { label: "SIAGA",   emoji: "🟠", color: "#f97316", desc: "Bersiap untuk evakuasi jika diperlukan" },
    bahaya:  { label: "BAHAYA",  emoji: "🔴", color: "#ef4444", desc: "Segera lakukan evakuasi ke tempat aman" },
  };
  return map[level] || map.waspada;
}

export function humanizeWaterLevel(cm) {
  if (!cm) return "Data tidak tersedia";
  if (cm < 50)  return `${cm} cm — Di bawah lutut`;
  if (cm < 100) return `${cm} cm — Setinggi lutut orang dewasa`;
  if (cm < 150) return `${cm} cm — Setinggi pinggang orang dewasa`;
  if (cm < 200) return `${cm} cm — Setinggi dada orang dewasa`;
  return `${cm} cm — Di atas kepala ⚠️ SANGAT BERBAHAYA`;
}

export function humanizeRainfall(mmPerHour) {
  if (!mmPerHour) return "Tidak ada hujan";
  if (mmPerHour < 5)   return "Gerimis ringan";
  if (mmPerHour < 20)  return "Hujan sedang";
  if (mmPerHour < 50)  return "Hujan lebat";
  if (mmPerHour < 100) return "⚠️ Hujan sangat lebat";
  return "🚨 Hujan ekstrem — Potensi banjir bandang";
}
