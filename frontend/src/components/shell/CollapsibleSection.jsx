import { useState } from "react";

/* ── CollapsibleSection — progressive disclosure per the FloodGuard spec ───
   Secondary content stays hidden behind a compact, tappable teaser row until
   the user asks for it. Collapsed = the SectionTeaser look; expanded = same
   header (now a collapse affordance) + children below.
*/
export default function CollapsibleSection({
  icon,
  iconBg,
  iconColor,
  title,
  subtitle,
  defaultOpen = false,
  open: openProp,   // optional: pass it (with onToggle) to open the section from outside
  onToggle,
  id,
  children,
}) {
  const [openState, setOpen] = useState(defaultOpen);
  const open = openProp ?? openState;

  const toggle = () => {
    const next = !open;
    if (openProp === undefined) setOpen(next);
    onToggle?.(next);
  };

  return (
    <section className="collapsible-section" id={id}>
      <button
        className="panel panel-body section-teaser"
        aria-expanded={open}
        onClick={toggle}
      >
        <div className="section-teaser-icon" style={{ background: iconBg, color: iconColor }}>
          {icon}
        </div>
        <div style={{ textAlign: "left", minWidth: 0 }}>
          <div className="section-teaser-title">{title}</div>
          {subtitle && <div className="section-teaser-sub">{subtitle}</div>}
        </div>
        <span
          className="section-teaser-chevron"
          style={{ color: iconColor, transform: open ? "rotate(180deg)" : "none" }}
        >
          ▾
        </span>
      </button>
      {open && <div className="collapsible-section-body">{children}</div>}
    </section>
  );
}
