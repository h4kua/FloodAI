import { useState, useEffect, useCallback, useRef } from "react";
import { useT, useApp } from "../lib/appContext";
import { getDeviceId, getProfile, setProfile, getFamilyCode, setFamilyCode } from "../lib/deviceIdentity";
import ChatBot from "../components/ChatBot";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const POLL_MS = 30_000;

const STATUS_LABEL_KEY = { safe: "family.statusSafe", in_transit: "family.statusInTransit", missing: "family.statusMissing" };

function timeAgo(isoString, lang) {
  if (!isoString) return "";
  const mins = Math.round((Date.now() - new Date(isoString).getTime()) / 60000);
  if (mins < 1) return lang === "en" ? "just now" : "baru saja";
  if (mins < 60) return lang === "en" ? `${mins}m ago` : `${mins}mnt lalu`;
  return lang === "en" ? `${Math.round(mins / 60)}h ago` : `${Math.round(mins / 60)}jam lalu`;
}

export default function FamilyStatus({ riskLevel = "waspada", rainfall = 0 }) {
  const t = useT();
  const { lang } = useApp();
  const deviceId = getDeviceId();

  const [familyCode, setFamilyCodeState] = useState(getFamilyCode());
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [busyDeviceId, setBusyDeviceId] = useState(null);

  const [mode, setMode] = useState("create"); // "create" | "join"
  const [name, setName] = useState(getProfile().name || "");
  const [phone, setPhone] = useState(getProfile().phone || "");
  const [joinCodeInput, setJoinCodeInput] = useState("");
  const [formError, setFormError] = useState("");
  const [formBusy, setFormBusy] = useState(false);

  const pollRef = useRef(null);

  const fetchMembers = useCallback(async (code) => {
    if (!code) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/family/${code}/members`);
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      setMembers(data.members || []);
    } catch (e) {
      setError(lang === "en" ? "Failed to load family status." : "Gagal memuat status keluarga.");
    } finally {
      setLoading(false);
    }
  }, [lang]);

  useEffect(() => {
    if (!familyCode) return;
    fetchMembers(familyCode);
    pollRef.current = setInterval(() => fetchMembers(familyCode), POLL_MS);
    return () => clearInterval(pollRef.current);
  }, [familyCode, fetchMembers]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setFormBusy(true);
    setFormError("");
    try {
      const res = await fetch(`${API_BASE}/family/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: deviceId, display_name: name.trim(), phone: phone.trim() || null }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      setProfile({ name: name.trim(), phone: phone.trim() });
      setFamilyCode(data.family_code);
      setFamilyCodeState(data.family_code);
    } catch (e) {
      setFormError(lang === "en" ? "Failed to create family." : "Gagal membuat keluarga.");
    } finally {
      setFormBusy(false);
    }
  };

  const handleJoin = async (e) => {
    e.preventDefault();
    const code = joinCodeInput.trim().toUpperCase();
    if (!name.trim() || code.length !== 6) return;
    setFormBusy(true);
    setFormError("");
    try {
      const res = await fetch(`${API_BASE}/family/join`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ family_code: code, device_id: deviceId, display_name: name.trim(), phone: phone.trim() || null }),
      });
      if (!res.ok) throw new Error(res.status === 404 ? "not_found" : `${res.status}`);
      setProfile({ name: name.trim(), phone: phone.trim() });
      setFamilyCode(code);
      setFamilyCodeState(code);
    } catch (e) {
      setFormError(e.message === "not_found"
        ? (lang === "en" ? "Family code not found." : "Kode keluarga tidak ditemukan.")
        : (lang === "en" ? "Failed to join family." : "Gagal bergabung ke keluarga."));
    } finally {
      setFormBusy(false);
    }
  };

  const handleLeave = () => {
    setFamilyCode("");
    setFamilyCodeState("");
    setMembers([]);
  };

  const updateMyStatus = async (status) => {
    setBusyDeviceId(deviceId);
    const finish = (lat, lon) => {
      fetch(`${API_BASE}/family/${familyCode}/checkin`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: deviceId, status, lat, lon }),
      })
        .then(() => fetchMembers(familyCode))
        .finally(() => setBusyDeviceId(null));
    };
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => finish(pos.coords.latitude, pos.coords.longitude),
        () => finish(null, null),
        { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 }
      );
    } else {
      finish(null, null);
    }
  };

  const sosForMember = async (member) => {
    setBusyDeviceId(member.device_id);
    try {
      const pos = await new Promise((resolve, reject) =>
        navigator.geolocation
          ? navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: true, timeout: 8000 })
          : reject(new Error("no_geo"))
      );
      await fetch(`${API_BASE}/sos`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          device_id: deviceId,
          family_code: familyCode,
          name: member.display_name,
          phone: member.phone || "-",
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          on_behalf_of_member_id: member.id,
        }),
      });
      await fetchMembers(familyCode);
    } catch {
      // Best-effort — the SOS page remains the primary path if this fails.
    } finally {
      setBusyDeviceId(null);
    }
  };

  if (!familyCode) {
    return (
      <>
        <div className="page-header fade-in">
          <h1 className="page-title">{t("family.title")}</h1>
        </div>
        <div className="panel panel-body fade-in" style={{ maxWidth: 420 }}>
          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
            <button className={`btn ${mode === "create" ? "" : "btn-ghost"}`} style={mode === "create" ? { background: "var(--cyan-soft)", color: "var(--cyan)", border: "1px solid var(--cyan-border)" } : undefined} onClick={() => setMode("create")}>
              {t("family.createTab")}
            </button>
            <button className={`btn ${mode === "join" ? "" : "btn-ghost"}`} style={mode === "join" ? { background: "var(--cyan-soft)", color: "var(--cyan)", border: "1px solid var(--cyan-border)" } : undefined} onClick={() => setMode("join")}>
              {t("family.joinTab")}
            </button>
          </div>
          <form onSubmit={mode === "create" ? handleCreate : handleJoin} style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
            {mode === "join" && (
              <input type="text" placeholder={t("family.codePlaceholder")} value={joinCodeInput}
                onChange={(e) => setJoinCodeInput(e.target.value.toUpperCase())} maxLength={6}
                className="route-input" style={{ width: "100%", textTransform: "uppercase", letterSpacing: "0.1em" }} />
            )}
            <input type="text" placeholder={t("family.nameLabel")} value={name} onChange={(e) => setName(e.target.value)} className="route-input" style={{ width: "100%" }} />
            <input type="tel" placeholder={t("family.phoneLabel")} value={phone} onChange={(e) => setPhone(e.target.value)} className="route-input" style={{ width: "100%" }} />
            <button type="submit" className="btn" style={{ background: "var(--cyan-soft)", color: "var(--cyan)", border: "1px solid var(--cyan-border)" }} disabled={formBusy}>
              {formBusy ? t("family.working") : mode === "create" ? t("family.create") : t("family.join")}
            </button>
            {formError && <p style={{ color: "var(--s1)", fontSize: "0.78rem" }}>{formError}</p>}
          </form>
        </div>
        <ChatBot riskContext={{ level: riskLevel, rainfall }} />
      </>
    );
  }

  return (
    <>
      <div className="page-header fade-in">
        <div>
          <h1 className="page-title">{t("family.title")}</h1>
          <p style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.7rem", color: "var(--muted-2)", marginTop: "0.25rem" }}>
            {t("family.yourCode")}: <strong style={{ color: "var(--cyan)", letterSpacing: "0.1em" }}>{familyCode}</strong>
          </p>
        </div>
        <button className="btn btn-ghost" onClick={handleLeave}>{t("family.leave")}</button>
      </div>

      <div className="panel panel-body fade-in" style={{ marginBottom: "0.875rem" }}>
        <p className="panel-title">{t("family.myStatus")}</p>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          {["safe", "in_transit", "missing"].map((s) => (
            <button key={s} className="btn btn-ghost" onClick={() => updateMyStatus(s)} disabled={busyDeviceId === deviceId}>
              {t(STATUS_LABEL_KEY[s])}
            </button>
          ))}
        </div>
      </div>

      <div className="panel panel-body fade-in">
        <p className="panel-title">{t("family.members")}</p>
        {loading && members.length === 0 && <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>{t("family.loading")}</p>}
        {error && <p style={{ color: "var(--s1)", fontSize: "0.85rem" }}>{error}</p>}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {members.map((m) => (
            <div key={m.id} className={`family-member-item ${m.status}`}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
                  <span className="family-member-dot" />
                  <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{m.display_name}</span>
                  {m.device_id === deviceId && <span style={{ fontSize: "0.65rem", color: "var(--muted-2)" }}>({t("family.you")})</span>}
                </div>
                <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.63rem", color: "var(--muted-2)", marginTop: "0.2rem" }}>
                  {t(STATUS_LABEL_KEY[m.status])} · {m.location_label || t("family.noLocation")} · {timeAgo(m.last_seen_at, lang)}
                  {m.is_stale ? ` · ${t("family.stale")}` : ""}
                </div>
              </div>
              {m.status === "missing" && m.device_id !== deviceId && (
                <button className="btn" style={{ background: "var(--s1-soft)", color: "var(--s1)", border: "1px solid var(--s1-border)" }}
                  onClick={() => sosForMember(m)} disabled={busyDeviceId === m.device_id}>
                  {busyDeviceId === m.device_id ? "..." : t("family.sosFor", { name: m.display_name })}
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      <ChatBot riskContext={{ level: riskLevel, rainfall }} />
    </>
  );
}
