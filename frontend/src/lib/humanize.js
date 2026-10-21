const LEVELS = {
  id: {
    aman:    { label: "Aman",    color: "var(--safe)", desc: "Tidak ada risiko banjir yang terdeteksi saat ini." },
    waspada: { label: "Waspada", color: "var(--wsp)",  desc: "Risiko banjir sedang. Pantau perkembangan cuaca." },
    siaga:   { label: "Siaga",   color: "#f97316",     desc: "Risiko tinggi. Bersiap evakuasi jika diperlukan." },
    bahaya:  { label: "Bahaya",  color: "var(--s1)",   desc: "Risiko sangat tinggi. Evakuasi segera ke lokasi aman." },
  },
  en: {
    aman:    { label: "Safe",    color: "var(--safe)", desc: "No flood risk detected at this time." },
    waspada: { label: "Watch", color: "var(--wsp)",  desc: "Moderate flood risk. Monitor weather updates." },
    siaga:   { label: "Alert",   color: "#f97316",     desc: "High risk. Prepare to evacuate if needed." },
    bahaya:  { label: "Danger",  color: "var(--s1)",   desc: "Very high risk. Evacuate immediately to a safe location." },
  },
};

export function humanizeRiskLevel(level, lang = "id") {
  const map = LEVELS[lang] ?? LEVELS.id;
  return map[level] ?? map.waspada;
}

export function humanizeRainfall(mmPerHour, lang = "id") {
  if (!mmPerHour || mmPerHour === 0) return lang === "en" ? "No rain"          : "Tidak ada hujan";
  if (mmPerHour < 5)                 return lang === "en" ? "Drizzle"          : "Gerimis";
  if (mmPerHour < 20)                return lang === "en" ? "Moderate rain"    : "Hujan sedang";
  if (mmPerHour < 50)                return lang === "en" ? "Heavy rain"       : "Hujan lebat";
  if (mmPerHour < 100)               return lang === "en" ? "Very heavy rain"  : "Hujan sangat lebat";
  return lang === "en" ? "Extreme rain" : "Hujan ekstrem";
}
