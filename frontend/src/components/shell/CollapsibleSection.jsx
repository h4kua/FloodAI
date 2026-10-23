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
  onToggle,
  children,
}) {
  const [open, setOpen] = useState(defaultOpen);

  const toggle = () => {
    setOpen((prev) => {
      const next = !prev;
      onToggle?.(next);
      return next;
    });
  };

  return (
    <section className="collapsible-section">
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
