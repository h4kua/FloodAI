export default function LoadingSpinner({ message = "Sedang memuat data..." }) {
  return (
    <div style={{ textAlign: "center", padding: "48px 16px", color: "#94a3b8" }}>
      <div
        style={{
          width: "40px",
          height: "40px",
          border: "4px solid #334155",
          borderTop: "4px solid #60a5fa",
          borderRadius: "50%",
          animation: "spin 1s linear infinite",
          margin: "0 auto 16px",
        }}
      />
      <p style={{ margin: 0, fontSize: "16px" }}>{message}</p>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
