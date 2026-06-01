export function humanizeRiskLevel(level) {
  const map = {
    aman: {
      label: "AMAN",
      color: "var(--safe)",
      desc: "Tidak ada risiko banjir yang terdeteksi saat ini.",
      recommendation: "Kondisi normal. Pantau pembaruan berkala.",
    },
    waspada: {
      label: "WASPADA",
      color: "var(--warning)",
      desc: "Risiko banjir sedang. Pantau perkembangan cuaca.",
      recommendation: "Siapkan barang penting. Ikuti perkembangan cuaca.",
    },
    siaga: {
      label: "SIAGA",
      color: "#f97316",
      desc: "Risiko tinggi. Bersiap evakuasi jika diperlukan.",
      recommendation: "Siapkan tas darurat. Ikuti arahan petugas BPBD.",
    },
    bahaya: {
      label: "BAHAYA",
      color: "var(--danger)",
      desc: "Risiko sangat tinggi. Evakuasi segera ke lokasi aman.",
      recommendation: "Evakuasi sekarang. Hubungi BPBD 117 atau Basarnas 115.",
    },
  };
  return map[level] ?? map.waspada;
}

export function humanizeRainfall(mmPerHour) {
  if (!mmPerHour || mmPerHour === 0) return "Tidak ada hujan";
  if (mmPerHour < 5)   return "Gerimis";
  if (mmPerHour < 20)  return "Hujan sedang";
  if (mmPerHour < 50)  return "Hujan lebat";
  if (mmPerHour < 100) return "Hujan sangat lebat";
  return "Hujan ekstrem";
}
