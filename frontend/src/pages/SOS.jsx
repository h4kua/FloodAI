import { useState, useRef, useCallback } from "react";
import { useT, useApp } from "../lib/appContext";
import { getDeviceId, getProfile, setProfile, getFamilyCode } from "../lib/deviceIdentity";
import ChatBot from "../components/ChatBot";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const HOLD_MS = 3000;
const RING_RADIUS = 80;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

export default function SOS({ riskLevel = "waspada", rainfall = 0 }) {
  const t = useT();
  const { lang } = useApp();
  const profile = getProfile();

  const [name, setName] = useState(profile.name || "");
  const [phone, setPhone] = useState(profile.phone || "");
  const needsProfile = !profile.name || !profile.phone;

  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState("idle"); // idle | dispatching | success | error
  const [errorMsg, setErrorMsg] = useState("");
  const rafRef = useRef(null);
  const startRef = useRef(0);

  const cancelHold = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    setProgress(0);
  }, []);

  const dispatch = useCallback(() => {
    setStatus("dispatching");
    if (!navigator.geolocation) {
      setStatus("error");
      setErrorMsg(lang === "en" ? "Geolocation not supported." : "Geolocation tidak didukung.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const res = await fetch(`${API_BASE}/sos`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              device_id: getDeviceId(),
              name: name.trim(),
              phone: phone.trim(),
              lat: pos.coords.latitude,
              lon: pos.coords.longitude,
              family_code: getFamilyCode() || null,
            }),
          });
          if (!res.ok) throw new Error(`${res.status}`);
          setProfile({ name: name.trim(), phone: phone.trim() });
          setStatus("success");
        } catch (e) {
          setStatus("error");
          setErrorMsg(lang === "en" ? "Failed to dispatch SOS." : "Gagal mengirim SOS.");
        }
      },
      () => {
        setStatus("error");
        setErrorMsg(lang === "en" ? "Location access denied." : "Akses lokasi ditolak.");
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  }, [name, phone, lang]);

  const startHold = useCallback(() => {
    if (needsProfile || status === "dispatching") return;
    startRef.current = performance.now();
    const step = (now) => {
      const elapsed = now - startRef.current;
      const pct = Math.min(1, elapsed / HOLD_MS);
      setProgress(pct);
      if (pct >= 1) {
        rafRef.current = null;
        dispatch();
        return;
      }
      rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
  }, [needsProfile, status, dispatch]);

  const reset = () => {
    setStatus("idle");
    setErrorMsg("");
    cancelHold();
  };

  const dashOffset = RING_CIRCUMFERENCE * (1 - progress);

  return (
    <>
      <div className="page-header fade-in">
        <h1 className="page-title" style={{ color: "var(--s1)" }}>{t("sos.title")}</h1>
      </div>

      {needsProfile && status === "idle" && (
        <div className="panel panel-body fade-in" style={{ maxWidth: 420, marginBottom: "1rem" }}>
          <p className="panel-title">{t("sos.profileTitle")}</p>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
            <input type="text" placeholder={t("sos.namePlaceholder")} value={name} onChange={(e) => setName(e.target.value)} className="route-input" style={{ width: "100%" }} />
            <input type="tel" placeholder={t("sos.phonePlaceholder")} value={phone} onChange={(e) => setPhone(e.target.value)} className="route-input" style={{ width: "100%" }} />
          </div>
        </div>
      )}

      <div className="panel panel-body fade-in" style={{ textAlign: "center", padding: "2.5rem 1rem" }}>
        {status === "idle" && (
          <>
            <p style={{ color: "var(--muted)", fontSize: "0.85rem", marginBottom: "1.75rem" }}>
              {t("sos.instructions")}
            </p>
            <div className="sos-button-wrap">
              <span className="sos-ring" />
              <span className="sos-ring r2" />
              <span className="sos-ring r3" />
              <svg className="sos-progress-ring" width={180} height={180} viewBox="0 0 180 180">
                <circle cx="90" cy="90" r={RING_RADIUS} strokeDasharray={RING_CIRCUMFERENCE} strokeDashoffset={dashOffset} />
              </svg>
              <button
                className="sos-button"
                onPointerDown={startHold}
                onPointerUp={cancelHold}
                onPointerLeave={cancelHold}
                disabled={needsProfile || (!name.trim() || !phone.trim())}
              >
                SOS
              </button>
            </div>
            <p style={{ color: "var(--muted-2)", fontSize: "0.76rem", marginTop: "1.5rem" }}>
              {t("sos.holdHint")}
            </p>
          </>
        )}

        {status === "dispatching" && (
          <p style={{ color: "var(--s1)", fontSize: "0.95rem", fontWeight: 700 }}>{t("sos.dispatching")}</p>
        )}

        {status === "success" && (
          <div>
            <div style={{ fontSize: "3rem", color: "var(--safe)", marginBottom: "0.5rem" }}>✓</div>
            <p style={{ color: "var(--safe)", fontSize: "1.1rem", fontWeight: 700, marginBottom: "0.5rem" }}>{t("sos.dispatched")}</p>
            <p style={{ color: "var(--muted)", fontSize: "0.8rem", marginBottom: "1.25rem" }}>{t("sos.dispatchedSub")}</p>
            <button className="btn btn-ghost" onClick={reset}>{t("sos.reset")}</button>
          </div>
        )}

        {status === "error" && (
          <div>
            <p style={{ color: "var(--s1)", fontSize: "0.9rem", marginBottom: "1rem" }}>{errorMsg}</p>
            <button className="btn btn-ghost" onClick={reset}>{t("sos.retry")}</button>
          </div>
        )}
      </div>

      <ChatBot riskContext={{ level: riskLevel, rainfall }} />
    </>
  );
}
