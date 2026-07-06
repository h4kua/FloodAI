import { useT } from "../../lib/appContext";
import { NAV_ITEMS } from "./navConfig";

/* ── Bottom navigation (mobile ≤768px) ─────────────────────────────────────
   Persistent flat navigation per the FloodGuard HCI spec: no critical
   destination is ever more than one tap away. Always rendered; CSS shows it
   only on mobile. Icon + label on every tab — never color-only signaling.
*/
export default function BottomNav({ page, onNavigate }) {
  const t = useT();

  return (
    <nav className="bottom-nav" aria-label="Navigasi utama">
      {NAV_ITEMS.map((item) => (
        <button
          key={item.id}
          data-tour={item.tour}
          className={`bottom-nav-btn${page === item.id ? " active" : ""}`}
          aria-current={page === item.id ? "page" : undefined}
          onClick={() => onNavigate(item.id)}
        >
          {item.icon}
          <span className="bottom-nav-label">{t(item.labelKey)}</span>
        </button>
      ))}
    </nav>
  );
}
