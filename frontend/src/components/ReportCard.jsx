import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../lib/api";

const NAME_KEY = "deflood_comment_name";
const COMMENT_MAX = 300;

const icon = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.9, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true };
const ThumbUp = () => <svg {...icon}><path d="M7 10v11" /><path d="M15 5.9 14 10h5.8a2 2 0 0 1 1.9 2.6l-2.3 7A2 2 0 0 1 17.5 21H7V10l4-8a3 3 0 0 1 3 3.9z" /></svg>;
const ThumbDown = () => <svg {...icon}><path d="M17 14V3" /><path d="M9 18.1 10 14H4.2a2 2 0 0 1-1.9-2.6l2.3-7A2 2 0 0 1 6.5 3H17v11l-4 8a3 3 0 0 1-3-3.9z" /></svg>;
const Bubble = () => <svg {...icon}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>;
const Dots = () => <svg {...icon}><circle cx="5" cy="12" r="1.3" /><circle cx="12" cy="12" r="1.3" /><circle cx="19" cy="12" r="1.3" /></svg>;

function timeAgo(isoString, isId) {
  const mins = Math.round((Date.now() - new Date(isoString).getTime()) / 60000);
  if (mins < 1) return isId ? "baru saja" : "just now";
  if (mins < 60) return isId ? `${mins} mnt lalu` : `${mins} min ago`;
  const hours = Math.round(mins / 60);
  return isId ? `${hours} jam lalu` : `${hours} h ago`;
}

const postJson = (path, body) => fetch(`${API_BASE}${path}`, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

/* ── One community report: text, photo, reactions, comments and a ⋯ menu ───
   Votes are one per device (lib/device.js) and can be changed or taken back;
   they update at once and roll back if the server refuses. Comments load when
   opened. The menu shares a link that opens this report (?report=<id>).
*/
export default function ReportCard({ report: r, isId, deviceId, sevLabel, focused, onChange, onHide }) {
  const [note, setNote] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [flagging, setFlagging] = useState(false);
  const [showComments, setShowComments] = useState(false);
  const [comments, setComments] = useState(null);   // null = not loaded yet
  const [text, setText] = useState("");
  const [author, setAuthor] = useState(() => { try { return localStorage.getItem(NAME_KEY) || ""; } catch { return ""; } });
  const [sending, setSending] = useState(false);
  const cardRef = useRef(null);
  const menuRef = useRef(null);

  const shareUrl = `${window.location.origin}${window.location.pathname}?report=${r.id}`;

  useEffect(() => {
    if (focused) cardRef.current?.scrollIntoView({ block: "center" });
  }, [focused]);

  // Close the menu on an outside tap or Escape.
  useEffect(() => {
    if (!menuOpen) return undefined;
    const onDown = (e) => { if (!menuRef.current?.contains(e.target)) { setMenuOpen(false); setFlagging(false); } };
    const onKey = (e) => { if (e.key === "Escape") { setMenuOpen(false); setFlagging(false); } };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("pointerdown", onDown); document.removeEventListener("keydown", onKey); };
  }, [menuOpen]);

  const vote = async (value) => {
    if (!deviceId) { setNote(isId ? "Reaksi butuh penyimpanan browser yang aktif." : "Reactions need browser storage."); return; }
    const before = { likes: r.likes ?? 0, dislikes: r.dislikes ?? 0, my_vote: r.my_vote ?? 0 };
    const next = before.my_vote === value ? 0 : value;
    const guess = { ...before, my_vote: next };
    if (before.my_vote === 1) guess.likes -= 1;
    if (before.my_vote === -1) guess.dislikes -= 1;
    if (next === 1) guess.likes += 1;
    if (next === -1) guess.dislikes += 1;
    onChange({ ...r, ...guess });
    try {
      const res = await postJson(`/reports/${r.id}/vote`, { device_id: deviceId, value: next });
      if (!res.ok) throw new Error(String(res.status));
      onChange({ ...r, ...(await res.json()) });
      setNote("");
    } catch {
      onChange({ ...r, ...before });
      setNote(isId ? "Reaksi belum tersimpan. Coba lagi." : "Your reaction was not saved. Try again.");
    }
  };

  const toggleComments = async () => {
    const open = !showComments;
    setShowComments(open);
    if (open && comments === null) {
      try {
        const res = await fetch(`${API_BASE}/reports/${r.id}/comments`);
        if (!res.ok) throw new Error(String(res.status));
        setComments((await res.json()).comments ?? []);
      } catch {
        setComments([]);
        setNote(isId ? "Komentar belum bisa dimuat." : "Comments could not be loaded.");
      }
    }
  };

  const sendComment = async (e) => {
    e.preventDefault();
    if (!text.trim() || sending) return;
    setSending(true);
    try {
      const res = await postJson(`/reports/${r.id}/comments`, { message: text.trim(), author: author.trim() || null, device_id: deviceId });
      if (res.status === 429) throw new Error("rate");
      if (!res.ok) throw new Error(String(res.status));
      const { comment } = await res.json();
      setComments((list) => [...(list ?? []), comment]);
      onChange({ ...r, comment_count: (r.comment_count ?? 0) + 1 });
      setText("");
      try { localStorage.setItem(NAME_KEY, author.trim()); } catch { /* storage blocked */ }
      setNote("");
    } catch (err) {
      setNote(err.message === "rate"
        ? (isId ? "Terlalu banyak kiriman dari jaringan ini. Coba lagi sebentar." : "Too many posts from this network. Try again shortly.")
        : (isId ? "Komentar gagal dikirim. Coba lagi." : "The comment could not be sent. Try again."));
    } finally {
      setSending(false);
    }
  };

  const copyLink = async () => {
    setMenuOpen(false);
    try {
      await navigator.clipboard.writeText(shareUrl);
      setNote(isId ? "Tautan disalin." : "Link copied.");
    } catch {
      setNote(shareUrl);
    }
  };

  const share = async () => {
    setMenuOpen(false);
    const body = `${sevLabel(r.severity)}: ${r.message.slice(0, 140)}${r.message.length > 140 ? "…" : ""}`;
    if (navigator.share) {
      try { await navigator.share({ title: "deFlood.ai", text: body, url: shareUrl }); return; } catch { return; /* closed by the user */ }
    }
    copyLink();
  };

  const flag = async (reason) => {
    setMenuOpen(false);
    setFlagging(false);
    try {
      const res = await postJson(`/reports/${r.id}/flag`, { device_id: deviceId, reason });
      if (!res.ok) throw new Error(String(res.status));
      onHide(r.id);
    } catch {
      setNote(isId ? "Belum bisa melaporkan. Coba lagi." : "Could not send the report. Try again.");
    }
  };

  const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${r.lat},${r.lon}`;
  const reasons = [
    ["wrong", isId ? "Info salah atau sudah tidak benar" : "Wrong or out of date"],
    ["spam", isId ? "Spam atau iklan" : "Spam or advertising"],
    ["offensive", isId ? "Kasar atau menyinggung" : "Abusive or offensive"],
    ["private", isId ? "Data pribadi orang lain" : "Someone's private data"],
  ];

  return (
    <li ref={cardRef} className={`report-item${r.is_pinned ? " report-pinned" : ""}${focused ? " report-focus" : ""}`}>
      <div className="report-head">
        <span className={`risk-badge badge-${r.severity === "alert" ? "s1" : "ok"}`}>{sevLabel(r.severity)}</span>
        <span className="report-meta">{timeAgo(r.created_at, isId)}</span>
        <div className="report-menu-wrap" ref={menuRef}>
          <button type="button" className="report-icon-btn" aria-haspopup="menu" aria-expanded={menuOpen}
            aria-label={isId ? "Pilihan lain" : "More options"} onClick={() => { setMenuOpen((o) => !o); setFlagging(false); }}>
            <Dots />
          </button>
          {menuOpen && (
            <div className="report-menu" role="menu">
              {!flagging ? (
                <>
                  <button type="button" role="menuitem" onClick={share}>{isId ? "Bagikan" : "Share"}</button>
                  <button type="button" role="menuitem" onClick={copyLink}>{isId ? "Salin tautan" : "Copy link"}</button>
                  <a role="menuitem" href={mapsUrl} target="_blank" rel="noopener noreferrer" onClick={() => setMenuOpen(false)}>
                    {isId ? "Lihat lokasi di Google Maps" : "See the place in Google Maps"}
                  </a>
                  <button type="button" role="menuitem" className="danger" onClick={() => setFlagging(true)}>
                    {isId ? "Laporkan laporan ini" : "Report this post"}
                  </button>
                </>
              ) : (
                <>
                  <p className="report-menu-title">{isId ? "Kenapa dilaporkan?" : "Why report it?"}</p>
                  {reasons.map(([key, label]) => (
                    <button type="button" role="menuitem" key={key} onClick={() => flag(key)}>{label}</button>
                  ))}
                </>
              )}
            </div>
          )}
        </div>
      </div>

      <p className="report-text">{r.message}</p>
      {r.photo_url && (
        <a href={r.photo_url} target="_blank" rel="noopener noreferrer" className="report-photo-link">
          <img className="report-photo" src={r.photo_url} loading="lazy" alt={isId ? "Foto dari pelapor" : "Photo from the reporter"} />
        </a>
      )}
      <p className="report-meta">
        {r.reporter_name || (isId ? "Anonim" : "Anonymous")}
        {" · "}
        {r.verified ? (isId ? "Terverifikasi" : "Verified") : (isId ? "Belum diverifikasi" : "Unverified")}
        {r.is_pinned ? (isId ? " · Terdekat dari Anda" : " · Nearest to you") : ""}
      </p>

      <div className="report-actions-row">
        <button type="button" className={`report-react${r.my_vote === 1 ? " is-on" : ""}`} aria-pressed={r.my_vote === 1}
          aria-label={isId ? `Suka (${r.likes ?? 0})` : `Like (${r.likes ?? 0})`} onClick={() => vote(1)}>
          <ThumbUp /><span>{r.likes ?? 0}</span>
        </button>
        <button type="button" className={`report-react is-down${r.my_vote === -1 ? " is-on" : ""}`} aria-pressed={r.my_vote === -1}
          aria-label={isId ? `Tidak suka (${r.dislikes ?? 0})` : `Dislike (${r.dislikes ?? 0})`} onClick={() => vote(-1)}>
          <ThumbDown /><span>{r.dislikes ?? 0}</span>
        </button>
        <button type="button" className={`report-react${showComments ? " is-on" : ""}`} aria-expanded={showComments}
          aria-label={isId ? `Komentar (${r.comment_count ?? 0})` : `Comments (${r.comment_count ?? 0})`} onClick={toggleComments}>
          <Bubble /><span>{r.comment_count ?? 0}</span>
        </button>
      </div>
      {note && <p className="report-note" role="status">{note}</p>}

      {showComments && (
        <div className="report-comments">
          {comments === null && <p className="report-meta">{isId ? "Memuat komentar…" : "Loading comments…"}</p>}
          {comments?.length === 0 && <p className="report-meta">{isId ? "Belum ada komentar." : "No comments yet."}</p>}
          {comments?.length > 0 && (
            <ul className="comment-list">
              {comments.map((c) => (
                <li key={c.id}>
                  <p className="comment-head"><strong>{c.author || (isId ? "Anonim" : "Anonymous")}</strong> · {timeAgo(c.created_at, isId)}</p>
                  <p className="comment-text">{c.message}</p>
                </li>
              ))}
            </ul>
          )}
          <form className="comment-form" onSubmit={sendComment}>
            <input className="route-input" type="text" maxLength={80} value={author} onChange={(e) => setAuthor(e.target.value)}
              placeholder={isId ? "Nama (opsional)" : "Name (optional)"} aria-label={isId ? "Nama" : "Name"} />
            <div className="comment-send-row">
              <input className="route-input" type="text" maxLength={COMMENT_MAX} value={text} onChange={(e) => setText(e.target.value)}
                placeholder={isId ? "Tulis komentar…" : "Write a comment…"} aria-label={isId ? "Komentar" : "Comment"} />
              <button type="submit" className="btn" disabled={sending || !text.trim()}>{isId ? "Kirim" : "Send"}</button>
            </div>
          </form>
        </div>
      )}
    </li>
  );
}
