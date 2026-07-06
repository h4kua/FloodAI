/* ── Shared navigation config ──────────────────────────────────────────────
   Single source of truth for the app's 4 destinations, consumed by both
   TopBar (desktop, labels only) and BottomNav (mobile, icon + label).
   `tour` is the data-tour attribute the OnboardingTour anchors to — both
   navs carry it; the tour picks whichever element is visible.
*/

const stroke = { fill: "none", stroke: "currentColor", strokeWidth: 1.9, strokeLinecap: "round", strokeLinejoin: "round" };

export const NAV_ITEMS = [
  {
    id: "home",
    labelKey: "nav.home",
    tour: "nav-home",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" {...stroke} aria-hidden="true">
        <path d="M3 10.5 12 3l9 7.5" />
        <path d="M5 9.5V21h14V9.5" />
        <path d="M9 21v-6h6v6" />
      </svg>
    ),
  },
  {
    id: "alert",
    labelKey: "nav.evac",
    tour: "nav-evac",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" {...stroke} aria-hidden="true">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    ),
  },
  {
    id: "reports",
    labelKey: "nav.reports",
    tour: "nav-reports",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" {...stroke} aria-hidden="true">
        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
      </svg>
    ),
  },
  {
    id: "about",
    labelKey: "nav.about",
    tour: "nav-about",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" {...stroke} aria-hidden="true">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="16" x2="12" y2="12" />
        <line x1="12" y1="8" x2="12.01" y2="8" />
      </svg>
    ),
  },
];
