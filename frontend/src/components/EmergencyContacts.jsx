const contacts = [
  { name: "BPBD Nasional", number: "117", icon: "🏛️" },
  { name: "Basarnas",       number: "115", icon: "🚁" },
  { name: "Ambulans",       number: "118", icon: "🚑" },
  { name: "Pemadam",        number: "113", icon: "🚒" },
];

export default function EmergencyContacts() {
  return (
    <div
      style={{
        background: "#450a0a",
        border: "1px solid #dc2626",
        borderRadius: "12px",
        padding: "16px",
      }}
    >
      <p style={{ color: "#fca5a5", fontWeight: "bold", margin: "0 0 12px" }}>
        📞 Nomor Darurat
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
        {contacts.map((c) => (
          <a
            key={c.name}
            href={`tel:${c.number}`}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              background: "#7f1d1d",
              borderRadius: "8px",
              padding: "10px",
              color: "white",
              textDecoration: "none",
              minHeight: "44px",
            }}
          >
            <span style={{ fontSize: "24px" }}>{c.icon}</span>
            <div>
              <p style={{ fontSize: "11px", color: "#fca5a5", margin: 0 }}>{c.name}</p>
              <p style={{ fontWeight: "bold", margin: 0 }}>{c.number}</p>
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}
