"""
Deterministic geographic scoping for BMKG CAP alerts.

The realtime Jakarta pipeline must not treat national BMKG alerts as local
evidence. Filtering is lexical by design so it remains explainable and does
not depend on external geocoders at runtime.

Upstream watershed alerts (Bandung Barat, Bogor, Puncak, etc.) are flagged
separately — heavy rain in these areas increases Ciliwung/Citarum flow into
Jakarta within 3-6 hours and should influence the decision engine.
"""

from __future__ import annotations


_JAKARTA_TOKENS = (
    "dki jakarta",
    "jakarta",
    "jakarta barat",
    "jakarta pusat",
    "jakarta selatan",
    "jakarta timur",
    "jakarta utara",
    "kepulauan seribu",
)

# Upstream watershed areas draining into Jakarta via Ciliwung/Citarum.
# Rain here reaches Jakarta flood gates in ~3-6 hours.
_UPSTREAM_WATERSHED_TOKENS = (
    "cipongkor",
    "kiarapedes",
    "rongga",
    "serangpanjang",
    "bogor",
    "depok",
    "puncak",
    "ciawi",
    "katulampa",
    "bandung barat",
    "citarum",
    "ciliwung",
    "cimanuk",
    "sukabumi",
    "cianjur",
)


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").lower().replace("/", " ").split())


def is_jakarta_bmkg_alert(alert: dict) -> bool:
    area_desc = _normalize_text(alert.get("area_desc"))
    if area_desc:
        return any(token in area_desc for token in _JAKARTA_TOKENS)

    # Only GEOGRAPHIC fields decide locality. ``event`` is a hazard type
    # ("HUJAN SANGAT LEBAT"), not a place, so it is intentionally excluded.
    composite = _normalize_text(
        " ".join(
            [
                str(alert.get("headline") or ""),
                str(alert.get("description") or ""),
                str(alert.get("instruction") or ""),
            ]
        )
    )
    if composite:
        return any(token in composite for token in _JAKARTA_TOKENS)

    # No geographic information at all. Such an alert names no region to reject,
    # so treat it as local to the already location-scoped request rather than
    # discarding a potentially valid alert (e.g. {"severity": "extreme",
    # "event": "HUJAN SANGAT LEBAT"}).
    return True


def filter_jakarta_bmkg_alerts(alerts: list[dict] | None) -> list[dict]:
    return [alert for alert in (alerts or []) if is_jakarta_bmkg_alert(alert)]


def is_upstream_watershed_alert(alert: dict) -> bool:
    """Return True if the alert covers an upstream watershed area (Ciliwung/Citarum basin)."""
    composite = _normalize_text(
        " ".join([
            str(alert.get("area_desc") or ""),
            str(alert.get("headline") or ""),
            str(alert.get("description") or ""),
        ])
    )
    return any(token in composite for token in _UPSTREAM_WATERSHED_TOKENS)


def filter_upstream_watershed_alerts(alerts: list[dict] | None) -> list[dict]:
    """Return alerts that affect upstream watersheds feeding into Jakarta."""
    return [alert for alert in (alerts or []) if is_upstream_watershed_alert(alert)]
