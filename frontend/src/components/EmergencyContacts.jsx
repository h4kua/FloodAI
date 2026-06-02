import { useT } from "../lib/appContext";

export default function EmergencyContacts() {
  const t = useT();
  const contacts = [
    { org: "BPBD Nasional", number: "117", roleKey: "contacts.bpbd"     },
    { org: "Basarnas",      number: "115", roleKey: "contacts.basarnas" },
    { org: "Ambulans",      number: "118", roleKey: "contacts.ambulans" },
    { org: "Pemadam",       number: "113", roleKey: "contacts.damkar"   },
  ];

  return (
    <div className="emergency">
      <p className="sect-label" style={{ marginTop: 0 }}>{t("contacts.title")}</p>
      <div className="emergency-grid">
        {contacts.map((c) => (
          <a key={c.org} href={`tel:${c.number}`} className="contact-link">
            <span className="contact-org">{c.org}</span>
            <span className="contact-num">{c.number}</span>
            <span className="contact-role">{t(c.roleKey)}</span>
          </a>
        ))}
      </div>
    </div>
  );
}
