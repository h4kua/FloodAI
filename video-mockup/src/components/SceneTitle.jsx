import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { T, MONO, SANS } from "../tokens";

/**
 * Full-screen scene title card.
 * Covers entire canvas with dark bg for first ~55 frames, then fades out
 * to reveal the scene underneath.
 */
export function SceneTitle({ icon, tag, title, sub }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Full overlay fades out between frame 38–58
  const overlayOp = interpolate(frame, [0, 5, 38, 58], [1, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Content slides up & fades in quickly, then fades out with overlay
  const contentOp = interpolate(frame, [0, 14, 36, 55], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const contentY = spring({ frame, fps, from: 30, to: 0, config: { damping: 14, stiffness: 100 } });

  if (frame > 62) return null;

  return (
    <AbsoluteFill
      style={{
        pointerEvents: "none",
        background: "rgba(13, 17, 23, 0.97)",
        opacity: overlayOp,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 100,
      }}
    >
      {/* Grid texture */}
      <div style={{
        position: "absolute", inset: 0,
        backgroundImage: `
          linear-gradient(rgba(56,189,248,0.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(56,189,248,0.03) 1px, transparent 1px)
        `,
        backgroundSize: "80px 80px",
        pointerEvents: "none",
      }} />

      {/* Ambient glow */}
      <div style={{
        position: "absolute",
        width: 600, height: 600,
        borderRadius: "50%",
        background: "radial-gradient(circle, rgba(56,189,248,0.08) 0%, transparent 70%)",
        pointerEvents: "none",
      }} />

      {/* Content */}
      <div style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        opacity: contentOp,
        transform: `translateY(${contentY}px)`,
      }}>
        {/* Icon circle */}
        <div style={{
          width: 120, height: 120,
          borderRadius: "50%",
          background: "rgba(56,189,248,0.08)",
          border: `2px solid rgba(56,189,248,0.3)`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 52,
          marginBottom: 28,
          boxShadow: "0 0 60px rgba(56,189,248,0.2)",
        }}>{icon}</div>

        {/* Tag */}
        <div style={{
          fontFamily: MONO,
          fontSize: 16,
          color: T.cyan,
          letterSpacing: "0.22em",
          textTransform: "uppercase",
          marginBottom: 14,
        }}>{tag}</div>

        {/* Title */}
        <div style={{
          fontFamily: SANS,
          fontWeight: 800,
          fontSize: 72,
          color: T.text,
          letterSpacing: "-0.03em",
          lineHeight: 1,
          textAlign: "center",
          marginBottom: 16,
        }}>{title}</div>

        {/* Divider */}
        <div style={{
          width: 160, height: 3,
          background: `linear-gradient(90deg, transparent, ${T.cyan}, transparent)`,
          marginBottom: 18,
          boxShadow: `0 0 14px ${T.cyan}`,
        }} />

        {/* Sub */}
        <div style={{
          fontFamily: MONO,
          fontSize: 20,
          color: T.muted,
          letterSpacing: "0.06em",
          textAlign: "center",
        }}>{sub}</div>
      </div>
    </AbsoluteFill>
  );
}
