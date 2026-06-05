import { useRef, useEffect } from "react";

export function use3DTilt({ maxTilt = 8, perspective = 800, enableShine = true } = {}) {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    // Skip on touch devices to avoid issues with tap hover states
    const isTouch = window.matchMedia("(pointer: coarse)").matches;
    if (isTouch) return;

    el.style.perspective = `${perspective}px`;
    el.style.transformStyle = "preserve-3d";

    const handleMouseMove = (e) => {
      const rect = el.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const w = rect.width;
      const h = rect.height;

      // Coordinate from -0.5 to 0.5 relative to element center
      const px = (x / w) - 0.5;
      const py = (y / h) - 0.5;

      const rotateX = -py * maxTilt;
      const rotateY = px * maxTilt;

      el.style.setProperty("--tilt-x", `${rotateX.toFixed(2)}deg`);
      el.style.setProperty("--tilt-y", `${rotateY.toFixed(2)}deg`);
      el.style.setProperty("--tilt-z", "10px");

      if (enableShine) {
        const shineX = (x / w) * 100;
        const shineY = (y / h) * 100;
        el.style.setProperty("--shine-x", `${shineX.toFixed(1)}%`);
        el.style.setProperty("--shine-y", `${shineY.toFixed(1)}%`);
        el.style.setProperty("--shine-opacity", "0.15");
      }
    };

    const handleMouseLeave = () => {
      el.style.setProperty("--tilt-x", "0deg");
      el.style.setProperty("--tilt-y", "0deg");
      el.style.setProperty("--tilt-z", "0px");
      el.style.setProperty("--shine-opacity", "0");
    };

    el.addEventListener("mousemove", handleMouseMove);
    el.addEventListener("mouseleave", handleMouseLeave);

    return () => {
      el.removeEventListener("mousemove", handleMouseMove);
      el.removeEventListener("mouseleave", handleMouseLeave);
    };
  }, [maxTilt, perspective, enableShine]);

  return ref;
}
