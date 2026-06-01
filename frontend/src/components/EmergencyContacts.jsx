const contacts = [
  { org: "BPBD Nasional",  number: "117", role: "Badan Penanggulangan Bencana" },
  { org: "Basarnas",       number: "115", role: "Badan SAR Nasional" },
  { org: "Ambulans",       number: "118", role: "Layanan Medis Darurat" },
  { org: "Pemadam",        number: "113", role: "Dinas Pemadam Kebakaran" },
];

export default function EmergencyContacts() {
  return (
    <div className="emergency">
      <p className="section-label">Kontak Darurat</p>
      <div className="emergency-grid">
        {contacts.map((c) => (
          <a key={c.org} href={`tel:${c.number}`} className="contact-link">
            <span className="contact-org">{c.org}</span>
            <span className="contact-num">{c.number}</span>
            <span className="contact-role">{c.role}</span>
          </a>
        ))}
      </div>
    </div>
  );
}
