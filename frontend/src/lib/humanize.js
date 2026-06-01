export function humanizeRiskLevel(level) {
  const map = {
    aman: {
      label: "AMAN",
      color: "var(--aman)",
      desc: "Tidak ada risiko banjir yang terdeteksi saat ini.",
      recommendation: "Kondisi normal. Tetap pantau pembaruan berkala.",
    },
    waspada: {
      label: "WASPADA",
      color: "var(--waspada)",
      desc: "Risiko banjir rendah hingga sedang. Pantau perkembangan cuaca.",
      recommendation: "Siapkan barang penting dan waspadai perubahan cuaca.",
    },
    siaga: {
      label: "SIAGA",
      color: "var(--siaga)",
      desc: "Risiko banjir tinggi. Bersiap untuk evakuasi jika diperlukan.",
      recommendation: "Siapkan tas darurat dan ikuti arahan petugas BPBD.",
    },
    bahaya: {
      label: "BAHAYA",
      color: "var(--bahaya)",
      desc: "Risiko banjir sangat tinggi. Segera evakuasi ke lokasi aman.",
      recommendation: "Evakuasi segera. Hubungi BPBD 117 atau Basarnas 115.",
    },
  };
  return map[level] ?? map.waspada;
}

export function humanizeRainfall(mmPerHour) {
  if (!mmPerHour || mmPerHour === 0) return "Tidak ada hujan";
  if (mmPerHour < 5)   return "Gerimis ringan";
  if (mmPerHour < 20)  return "Hujan sedang";
  if (mmPerHour < 50)  return "Hujan lebat";
  if (mmPerHour < 100) return "Hujan sangat lebat";
  return "Hujan ekstrem";
}

export function humanizeWaterLevel(cm) {
  if (!cm) return "Tidak tersedia";
  if (cm < 50)  return `${cm} cm — Bawah lutut`;
  if (cm < 100) return `${cm} cm — Setinggi lutut`;
  if (cm < 150) return `${cm} cm — Setinggi pinggang`;
  if (cm < 200) return `${cm} cm — Setinggi dada`;
  return `${cm} cm — Di atas kepala`;
}
