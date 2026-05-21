"""
Hydrology Reasoning Upgrade — per-station severity scoring and explanation.

Replaces the single water_level_ratio scalar with a full HydrologyAssessment
that explains WHY conditions are critical, not just that a ratio was crossed.

Design:
  - Station thresholds from BPBD DKI Jakarta public operational data.
    Per-record numeric siaga1/siaga2/siaga3/siaga4 fields override defaults,
    so real Posko Banjir API responses with calibrated thresholds are handled.
  - Severity score: normal=0.0, siaga4=0.25, siaga3=0.50, siaga2=0.75, siaga1=1.00
  - Near-threshold: within 10% of the NEXT higher siaga level value (in cm)
  - Rapid escalation: water_level_delta feature > 0.10 normalised units
  - Aggregate severity: maximum across stations (worst-case dominates)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache

_log = logging.getLogger(__name__)

# ─── BPBD DKI Jakarta reference thresholds (cm) ──────────────────────────────
_STATION_THRESHOLDS: dict[str, dict[str, float]] = {
    "manggarai":    {"siaga1": 950.0, "siaga2": 850.0, "siaga3": 750.0, "siaga4": 650.0},
    "katulampa":    {"siaga1": 800.0, "siaga2": 670.0, "siaga3": 540.0, "siaga4": 360.0},
    "depok":        {"siaga1": 600.0, "siaga2": 500.0, "siaga3": 400.0, "siaga4": 300.0},
    "pesanggrahan": {"siaga1":  75.0, "siaga2":  60.0, "siaga3":  50.0, "siaga4":  40.0},
    "angke":        {"siaga1": 200.0, "siaga2": 170.0, "siaga3": 130.0, "siaga4": 100.0},
}

# Generic Jakarta fallback thresholds (cm) for stations with no calibrated
# reference, no per-record siaga values, and no AWLR match. Without this an
# unknown station reports "normal" for any water level (e.g. 280 cm), hiding
# real flood conditions. Conservative generic standard: erring toward alerting.
_GENERIC_DEFAULT_THRESHOLDS: dict[str, float] = {
    "siaga1": 250.0, "siaga2": 200.0, "siaga3": 150.0,
}

_SIAGA_SEVERITY: dict[str, float] = {
    "siaga1": 1.00, "siaga2": 0.75, "siaga3": 0.50, "siaga4": 0.25, "normal": 0.00,
}

_NEAR_THRESHOLD_MARGIN = 0.10   # within 10% of next siaga level value
_RAPID_DELTA_THRESHOLD = 0.10   # normalised ratio delta for rapid escalation


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


@lru_cache(maxsize=1)
def _awlr_payload() -> tuple:
    """Cached AWLR threshold gates (read-only, from data/raw cache). () on absence."""
    try:
        from services.awlr_threshold_fetcher import load_cached_thresholds

        payload = load_cached_thresholds()
        return tuple(payload.get("gates", [])) if payload else ()
    except Exception:  # noqa: BLE001 — threshold enrichment must never break analysis
        return ()


def _awlr_thresholds_for(station_id: str) -> dict[str, float]:
    """
    Derive per-station siaga thresholds (cm) from the public AWLR dataset, used
    as a fallback for stations not in _STATION_THRESHOLDS and without per-record
    siaga values.

    Only siaga1/siaga2/siaga3 LOWER bounds are derived — they are unambiguous in
    the AWLR bands (e.g. "> 350", "250 - 350", "150 - 250"). siaga4 ("< 150") has
    no defined lower bound, so it is intentionally omitted (sub-siaga3 readings
    stay "normal") rather than fabricating a boundary in a safety-critical path.
    """
    needle = (station_id or "").strip().lower()
    if not needle:
        return {}
    for gate in _awlr_payload():
        name = (gate.get("name") or "").lower()
        kali = (gate.get("kali") or "").lower()
        if not (needle in name or (name and name in needle) or needle in kali):
            continue
        out: dict[str, float] = {}
        s1 = gate.get("siaga1_cm")
        if isinstance(s1, (int, float)) and s1 > 0:
            out["siaga1"] = float(s1)
        for level, key in (("siaga2", "siaga_2"), ("siaga3", "siaga_3")):
            band = gate.get(key)
            if isinstance(band, dict) and isinstance(band.get("min"), (int, float)) and band["min"] > 0:
                out[level] = float(band["min"])
        return out
    return {}


def _resolve_thresholds(record: dict, station_id: str) -> dict[str, float]:
    # Reference stations (calibrated BPBD values) take precedence; for any other
    # station, fall back to AWLR-derived thresholds so it can still be assessed
    # against real per-gate values instead of going unscored.
    defaults = _STATION_THRESHOLDS.get(station_id.lower(), {})
    if not defaults:
        defaults = _awlr_thresholds_for(station_id)
    resolved = {
        k: _safe_float(record.get(k), defaults.get(k, 0.0))
        for k in ("siaga1", "siaga2", "siaga3", "siaga4")
    }
    resolved = {k: v for k, v in resolved.items() if v > 0}
    # Last resort: an unknown station with no thresholds at all would otherwise
    # report "normal" for any water level. Apply the generic Jakarta standard so
    # high levels (e.g. 280 cm -> Siaga 1) still surface.
    if not resolved:
        return dict(_GENERIC_DEFAULT_THRESHOLDS)
    return resolved


def _determine_siaga_level(tinggi_air: float, thresholds: dict[str, float]) -> str:
    for level in ("siaga1", "siaga2", "siaga3", "siaga4"):
        if level in thresholds and tinggi_air >= thresholds[level]:
            return level
    return "normal"


def _near_threshold(
    tinggi_air: float, siaga_level: str, thresholds: dict[str, float]
) -> tuple[bool, float, str]:
    next_map = {"normal": "siaga4", "siaga4": "siaga3", "siaga3": "siaga2", "siaga2": "siaga1", "siaga1": None}
    next_level = next_map.get(siaga_level)
    if not next_level or next_level not in thresholds:
        return False, 0.0, ""
    nxt_val = thresholds[next_level]
    margin = nxt_val - tinggi_air
    is_near = 0 <= margin <= nxt_val * _NEAR_THRESHOLD_MARGIN
    return is_near, round(margin, 1), next_level


# ─── Data structures ─────────────────────────────────────────────────────────

@dataclass
class StationAssessment:
    station_id: str
    station_name: str
    tinggi_air_cm: float
    siaga_level: str
    severity_score: float
    water_level_ratio: float
    near_threshold: bool
    near_threshold_margin_cm: float
    next_siaga_level: str
    thresholds: dict[str, float]
    explanation: str


@dataclass
class HydrologyAssessment:
    """
    Aggregated hydrology assessment across all Posko Banjir stations.
    Stored in PerceptionResult and exposed in pipeline output.
    """
    stations: list[StationAssessment] = field(default_factory=list)
    severity_score: float = 0.0
    dominant_station: str = ""
    dominant_siaga_level: str = "normal"
    critical_station_count: int = 0
    near_threshold_count: int = 0
    rapid_escalation: bool = False
    overall_explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "severity_score": round(self.severity_score, 4),
            "dominant_station": self.dominant_station,
            "dominant_siaga_level": self.dominant_siaga_level,
            "critical_station_count": self.critical_station_count,
            "near_threshold_count": self.near_threshold_count,
            "rapid_escalation": self.rapid_escalation,
            "overall_explanation": self.overall_explanation,
            "stations": [
                {
                    "station_id": s.station_id,
                    "station_name": s.station_name,
                    "tinggi_air_cm": s.tinggi_air_cm,
                    "siaga_level": s.siaga_level,
                    "severity_score": round(s.severity_score, 4),
                    "water_level_ratio": round(s.water_level_ratio, 4),
                    "near_threshold": s.near_threshold,
                    "near_threshold_margin_cm": s.near_threshold_margin_cm,
                    "next_siaga_level": s.next_siaga_level,
                    "explanation": s.explanation,
                }
                for s in self.stations
            ],
        }


# ─── Public API ───────────────────────────────────────────────────────────────

def analyze_hydrology(
    poskobanjir_records: list[dict],
    water_level_delta: float | None = None,
) -> HydrologyAssessment:
    """
    Full hydrology reasoning across all Posko Banjir station records.

    Args:
        poskobanjir_records: Raw list from snapshot["poskobanjir"].
        water_level_delta:   Normalised delta from feature_builder (ratio units).
    """
    if not poskobanjir_records:
        return HydrologyAssessment(
            overall_explanation="No Posko Banjir records — hydrology cannot be assessed.",
        )

    try:
        delta_value = (
            float(water_level_delta)
            if water_level_delta not in (None, "")
            else None
        )
    except (TypeError, ValueError):
        delta_value = None

    assessments: list[StationAssessment] = []
    for record in poskobanjir_records:
        sid   = str(record.get("id") or record.get("name") or "unknown").lower()
        sname = str(record.get("name") or sid)
        ta    = _safe_float(record.get("tinggi_air"))

        thresholds   = _resolve_thresholds(record, sid)
        siaga_level  = _determine_siaga_level(ta, thresholds)
        severity     = _SIAGA_SEVERITY.get(siaga_level, 0.0)
        s1_val       = thresholds.get("siaga1", 0.0)
        ratio        = min(ta / s1_val, 1.5) if s1_val > 0 else 0.0
        near, margin, next_lv = _near_threshold(ta, siaga_level, thresholds)

        if siaga_level == "siaga1":
            expl = (
                f"{sname}: {ta:.0f} cm — AT SIAGA 1 (critical). "
                "Flood conditions active at highest alert threshold."
            )
        elif siaga_level == "siaga2":
            expl = (
                f"{sname}: {ta:.0f} cm — Siaga 2 (severe). "
                + ("Approaching Siaga 1 — imminent escalation." if near else "High flood probability.")
            )
        elif siaga_level in ("siaga3", "siaga4"):
            near_msg = f" {margin:.0f} cm below {next_lv}." if near else ""
            expl = f"{sname}: {ta:.0f} cm — {siaga_level.capitalize()} (elevated).{near_msg}"
        else:
            near_msg = f" {margin:.0f} cm below first alert level." if near and margin > 0 else ""
            expl = f"{sname}: {ta:.0f} cm — Normal range.{near_msg}"

        assessments.append(StationAssessment(
            station_id=sid, station_name=sname, tinggi_air_cm=ta,
            siaga_level=siaga_level, severity_score=severity,
            water_level_ratio=round(ratio, 4),
            near_threshold=near, near_threshold_margin_cm=margin if near else 0.0,
            next_siaga_level=next_lv if near else "",
            thresholds=thresholds, explanation=expl,
        ))

    if not assessments:
        return HydrologyAssessment(
            overall_explanation="Records present but no valid station data extracted.",
        )

    dominant   = max(assessments, key=lambda s: (s.severity_score, s.water_level_ratio))
    crit_count = sum(1 for s in assessments if s.siaga_level in ("siaga1", "siaga2"))
    near_count = sum(1 for s in assessments if s.near_threshold)
    rapid      = delta_value is not None and delta_value > _RAPID_DELTA_THRESHOLD

    parts: list[str] = []
    if dominant.siaga_level == "siaga1":
        parts.append(
            f"CRITICAL: {dominant.station_name} at Siaga 1 ({dominant.tinggi_air_cm:.0f} cm). "
            "Immediate flood risk — highest alert."
        )
    elif dominant.siaga_level == "siaga2":
        parts.append(
            f"SEVERE: {dominant.station_name} at Siaga 2 ({dominant.tinggi_air_cm:.0f} cm). "
            "High flood probability — activate emergency protocols."
        )
    elif dominant.siaga_level == "siaga3":
        parts.append(f"ELEVATED: {dominant.station_name} at Siaga 3 — flood watch active.")
    elif dominant.siaga_level == "siaga4":
        parts.append(f"WATCH: {dominant.station_name} at Siaga 4 — early warning.")
    else:
        parts.append("All monitored stations within normal range.")

    if crit_count > 1:
        parts.append(f"{crit_count} stations at critical levels — compound hydrology risk.")
    if near_count:
        parts.append(f"{near_count} station(s) approaching next alert level.")
    if rapid:
        parts.append("Rapid water level escalation detected — possible upstream surge or tidal backflow.")
    elif delta_value is None:
        _log.debug("Hydrology rapid escalation check skipped because water_level_delta is unavailable.")
        parts.append("Rapid escalation check unavailable — water level delta is missing.")
    return HydrologyAssessment(
        stations=assessments,
        severity_score=round(dominant.severity_score, 4),
        dominant_station=dominant.station_name,
        dominant_siaga_level=dominant.siaga_level,
        critical_station_count=crit_count,
        near_threshold_count=near_count,
        rapid_escalation=rapid,
        overall_explanation=" ".join(parts),
    )

