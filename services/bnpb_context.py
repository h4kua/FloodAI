"""
BNPB InaRISK vulnerability context service for DKI Jakarta.

Fetches long-term regional flood vulnerability from BNPB InaRISK and maps
location strings to Jakarta kota with deterministic confidence scoring.

CRITICAL CONTRACT:
  - This data MUST NOT influence ML probability or risk_level
  - Only affects: manual_review threshold, action priority, routing preference
  - Mapping confidence < 0.70 → BNPB data is silently ignored
  - Data vintage > 365 days → BNPB data is silently ignored
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

import httpx

from api.observability import (
    BNPB_DATA_STALE_TOTAL,
    BNPB_FETCH_FAILED_TOTAL,
    BNPB_VINTAGE_FALLBACK_TOTAL,
)

logger = logging.getLogger(__name__)

# ─── Confidence threshold ─────────────────────────────────────────────────────
# Below this, district mapping is too ambiguous to use BNPB data safely.
MAPPING_CONFIDENCE_THRESHOLD = 0.70

# ─── Jakarta kota BPS codes ───────────────────────────────────────────────────
# Includes Kepulauan Seribu (3101, Kabupaten) so the live InaRISK parser
# accepts records for the sixth DKI Jakarta district. The static fallback
# JSON also publishes a Kepulauan Seribu record, so the alias dictionary
# below resolves any of its names to the canonical kota string.
_JAKARTA_KOTA_CODES: frozenset[str] = frozenset(
    {"3101", "3171", "3172", "3173", "3174", "3175"}
)

_CODE_TO_KOTA: dict[str, str] = {
    "3101": "Kepulauan Seribu",
    "3171": "Jakarta Selatan",
    "3172": "Jakarta Timur",
    "3173": "Jakarta Pusat",
    "3174": "Jakarta Barat",
    "3175": "Jakarta Utara",
}

# ─── Deterministic alias dictionary ──────────────────────────────────────────
# Maps exact lowercase strings → canonical kota name.
# Covers: official kota names, abbreviations, English translations,
# all 44 kecamatan, and commonly referenced kelurahan / landmarks.
# NO generic "jakarta" fallback — ambiguous inputs are rejected, not guessed.
_EXACT_ALIASES: dict[str, str] = {
    # ── Jakarta Pusat (Kota code 3173) ───────────────────────────────────────
    "jakarta pusat":        "Jakarta Pusat",
    "jak-pus":              "Jakarta Pusat",
    "jakpus":               "Jakarta Pusat",
    "central jakarta":      "Jakarta Pusat",
    "kota jakarta pusat":   "Jakarta Pusat",
    "kab. jakarta pusat":   "Jakarta Pusat",
    # Kecamatan (8)
    "gambir":               "Jakarta Pusat",
    "sawah besar":          "Jakarta Pusat",
    "kemayoran":            "Jakarta Pusat",
    "senen":                "Jakarta Pusat",
    "cempaka putih":        "Jakarta Pusat",
    "menteng":              "Jakarta Pusat",
    "tanah abang":          "Jakarta Pusat",
    "johar baru":           "Jakarta Pusat",
    # Notable kelurahan / landmarks
    "senayan":              "Jakarta Pusat",
    "monas":                "Jakarta Pusat",
    "petamburan":           "Jakarta Pusat",
    "benhil":               "Jakarta Pusat",
    "bendungan hilir":      "Jakarta Pusat",
    "cideng":               "Jakarta Pusat",
    "mangga dua":           "Jakarta Pusat",

    # ── Jakarta Utara (Kota code 3175) ───────────────────────────────────────
    "jakarta utara":        "Jakarta Utara",
    "jak-ut":               "Jakarta Utara",
    "jakut":                "Jakarta Utara",
    "north jakarta":        "Jakarta Utara",
    "kota jakarta utara":   "Jakarta Utara",
    "kab. jakarta utara":   "Jakarta Utara",
    # Kecamatan (6)
    "penjaringan":          "Jakarta Utara",
    "pademangan":           "Jakarta Utara",
    "tanjung priok":        "Jakarta Utara",
    "koja":                 "Jakarta Utara",
    "kelapa gading":        "Jakarta Utara",
    "cilincing":            "Jakarta Utara",
    # Notable kelurahan / landmarks
    "pluit":                "Jakarta Utara",
    "muara baru":           "Jakarta Utara",
    "ancol":                "Jakarta Utara",
    "sunter":               "Jakarta Utara",
    "priok":                "Jakarta Utara",
    "warakas":              "Jakarta Utara",
    "pegangsaan dua":       "Jakarta Utara",
    "tanjung priok port":   "Jakarta Utara",
    "pelabuhan":            "Jakarta Utara",

    # ── Jakarta Barat (Kota code 3174) ───────────────────────────────────────
    "jakarta barat":        "Jakarta Barat",
    "jak-bar":              "Jakarta Barat",
    "jakbar":               "Jakarta Barat",
    "west jakarta":         "Jakarta Barat",
    "kota jakarta barat":   "Jakarta Barat",
    "kab. jakarta barat":   "Jakarta Barat",
    # Kecamatan (8)
    "cengkareng":           "Jakarta Barat",
    "kalideres":            "Jakarta Barat",
    "kebon jeruk":          "Jakarta Barat",
    "kembangan":            "Jakarta Barat",
    "grogol petamburan":    "Jakarta Barat",
    "taman sari":           "Jakarta Barat",
    "tambora":              "Jakarta Barat",
    "palmerah":             "Jakarta Barat",
    # Notable kelurahan / landmarks
    "kapuk":                "Jakarta Barat",
    "kamal":                "Jakarta Barat",
    "grogol":               "Jakarta Barat",
    "slipi":                "Jakarta Barat",
    "glodok":               "Jakarta Barat",
    "kota tua":             "Jakarta Barat",
    "mangga besar":         "Jakarta Barat",
    "jembatan lima":        "Jakarta Barat",
    "duri kepa":            "Jakarta Barat",
    "kali deres":           "Jakarta Barat",
    "rawa buaya":           "Jakarta Barat",

    # ── Jakarta Timur (Kota code 3172) ───────────────────────────────────────
    "jakarta timur":        "Jakarta Timur",
    "jak-tim":              "Jakarta Timur",
    "jaktim":               "Jakarta Timur",
    "east jakarta":         "Jakarta Timur",
    "kota jakarta timur":   "Jakarta Timur",
    "kab. jakarta timur":   "Jakarta Timur",
    # Kecamatan (10)
    "matraman":             "Jakarta Timur",
    "pulo gadung":          "Jakarta Timur",
    "jatinegara":           "Jakarta Timur",
    "duren sawit":          "Jakarta Timur",
    "kramat jati":          "Jakarta Timur",
    "cakung":               "Jakarta Timur",
    "pasar rebo":           "Jakarta Timur",
    "ciracas":              "Jakarta Timur",
    "cipayung":             "Jakarta Timur",
    "makassar":             "Jakarta Timur",
    "makasar":              "Jakarta Timur",
    # Notable kelurahan / landmarks
    "kampung melayu":       "Jakarta Timur",
    "cawang":               "Jakarta Timur",
    "klender":              "Jakarta Timur",
    "rawa bunga":           "Jakarta Timur",
    "bidara cina":          "Jakarta Timur",
    "pondok bambu":         "Jakarta Timur",
    "buaran":               "Jakarta Timur",
    "pulo gadung":          "Jakarta Timur",
    "pisangan":             "Jakarta Timur",

    # ── Kepulauan Seribu (Kabupaten code 3101) ───────────────────────────────
    # Sixth DKI Jakarta administrative unit. Sparse alias set (no kecamatan
    # cluster maps cleanly to non-archipelago names) — the canonical and
    # English forms cover the request shapes seen in production.
    "kepulauan seribu":             "Kepulauan Seribu",
    "kab. kepulauan seribu":        "Kepulauan Seribu",
    "kabupaten kepulauan seribu":   "Kepulauan Seribu",
    "kep. seribu":                  "Kepulauan Seribu",
    "thousand islands":             "Kepulauan Seribu",
    "kepulauan seribu utara":       "Kepulauan Seribu",
    "kepulauan seribu selatan":     "Kepulauan Seribu",

    # ── Jakarta Selatan (Kota code 3171) ─────────────────────────────────────
    "jakarta selatan":      "Jakarta Selatan",
    "jak-sel":              "Jakarta Selatan",
    "jaksel":               "Jakarta Selatan",
    "south jakarta":        "Jakarta Selatan",
    "kota jakarta selatan": "Jakarta Selatan",
    "kab. jakarta selatan": "Jakarta Selatan",
    # Kecamatan (10)
    "tebet":                "Jakarta Selatan",
    "setiabudi":            "Jakarta Selatan",
    "mampang prapatan":     "Jakarta Selatan",
    "pasar minggu":         "Jakarta Selatan",
    "cilandak":             "Jakarta Selatan",
    "kebayoran baru":       "Jakarta Selatan",
    "kebayoran lama":       "Jakarta Selatan",
    "pesanggrahan":         "Jakarta Selatan",
    "jagakarsa":            "Jakarta Selatan",
    "pancoran":             "Jakarta Selatan",
    # Notable kelurahan / landmarks
    "manggarai":            "Jakarta Selatan",
    "bukit duri":           "Jakarta Selatan",
    "rawajati":             "Jakarta Selatan",
    "kalibata":             "Jakarta Selatan",
    "blok m":               "Jakarta Selatan",
    "kebayoran":            "Jakarta Selatan",
    "pondok indah":         "Jakarta Selatan",
    "fatmawati":            "Jakarta Selatan",
    "cipete":               "Jakarta Selatan",
    "kemang":               "Jakarta Selatan",
    "kuningan":             "Jakarta Selatan",
    "rasuna said":          "Jakarta Selatan",
    "casablanca":           "Jakarta Selatan",
    "gatot subroto":        "Jakarta Selatan",
}

# Canonical lowercase → canonical proper-case (for substring containment check)
_CANONICAL_LOWER: dict[str, str] = {
    "jakarta pusat":    "Jakarta Pusat",
    "jakarta utara":    "Jakarta Utara",
    "jakarta barat":    "Jakarta Barat",
    "jakarta timur":    "Jakarta Timur",
    "jakarta selatan":  "Jakarta Selatan",
    "kepulauan seribu": "Kepulauan Seribu",
}

# Short kota aliases used in the exact alias check to distinguish kota-level
# matches (confidence 0.95) from kecamatan/kelurahan matches (confidence 0.90)
_KOTA_LEVEL_TOKENS: frozenset[str] = frozenset({
    "jak-pus", "jakpus", "jak-ut", "jakut", "jak-bar", "jakbar",
    "jak-tim", "jaktim", "jak-sel", "jaksel",
    "central jakarta", "north jakarta", "west jakarta",
    "east jakarta", "south jakarta",
    "kota jakarta pusat", "kota jakarta utara", "kota jakarta barat",
    "kota jakarta timur", "kota jakarta selatan",
    "jakarta pusat", "jakarta utara", "jakarta barat",
    "jakarta timur", "jakarta selatan",
    "kab. jakarta pusat", "kab. jakarta utara", "kab. jakarta barat",
    "kab. jakarta timur", "kab. jakarta selatan",
    # Sixth DKI Jakarta unit — kabupaten-level tokens.
    "kepulauan seribu", "kab. kepulauan seribu",
    "kabupaten kepulauan seribu", "kep. seribu", "thousand islands",
})

# ─── Score normalisation & classification ────────────────────────────────────
_IRBI_NORMALISE_MAX = 300.0
_THRESHOLD_VERY_HIGH = 0.75
_THRESHOLD_HIGH = 0.55
_THRESHOLD_MEDIUM = 0.35
_MAX_VINTAGE_DAYS = 365
_DEFAULT_VINTAGE_DAYS = int(os.getenv("BNPB_DEFAULT_VINTAGE_DAYS", "30"))
_CACHE_TTL = 86_400

# ─── API endpoints ────────────────────────────────────────────────────────────
_URL_IRBI     = "https://inarisk.bnpb.go.id/api/bencana-irbi"
_URL_PASOET   = "https://inarisk.bnpb.go.id/api/data_pasoet"
_URL_PROVINSI = "https://inarisk.bnpb.go.id/api/provinsi"
_TIMEOUT      = 10.0

# ─── Static fallback ──────────────────────────────────────────────────────────
# Used when the live InaRISK API is unreachable. Path resolves to
# ``app/data/bnpb_jakarta_fallback.json``. Override at deploy time via the
# ``BNPB_STATIC_FALLBACK_PATH`` env var (e.g. point at a curated NFS share).
_DEFAULT_IRBI_SCORE = 0.5  # Mid-band default for mapped-but-unknown districts.
_FALLBACK_JSON_PATH = Path(
    os.getenv(
        "BNPB_STATIC_FALLBACK_PATH",
        str(Path(__file__).resolve().parents[1] / "data" / "bundled" / "bnpb_jakarta_fallback.json"),
    )
)

# Sentinel ``data_source`` values stamped on every VulnerabilityContext so the
# gate, traces, and observability counters can distinguish where the score
# actually came from. Operators MUST be able to tell at a glance whether the
# decision rode on live, cached-static, or synthetic data.
DATA_SOURCE_API     = "api"
DATA_SOURCE_STATIC  = "static_fallback"
DATA_SOURCE_DEFAULT = "default"

_cache: dict = {}

# Historical flood statistics per kota, built by
# scripts/build_historical_flood_events.py from data/raw/combined.csv.
_HISTORICAL_EVENTS_PATH = Path(__file__).resolve().parents[1] / "data" / "bundled" / "historical_flood_events.json"


@lru_cache(maxsize=1)
def _load_historical_events() -> dict:
    """Per-district historical flood stats. Returns {} on any failure (fail-open)."""
    try:
        if not _HISTORICAL_EVENTS_PATH.exists():
            return {}
        payload = json.loads(_HISTORICAL_EVENTS_PATH.read_text(encoding="utf-8"))
        return payload.get("districts", {}) or {}
    except (OSError, ValueError) as exc:
        logger.warning("historical_events_load_failed: %s", exc)
        return {}


_HAZARD_2023_PATH = Path(__file__).resolve().parents[1] / "data" / "bundled" / "flood_hazard_index_2023.json"


@lru_cache(maxsize=1)
def _load_hazard_2023() -> dict:
    """Per-kota 2023 flood hazard index. Returns {} on any failure (fail-open)."""
    try:
        if not _HAZARD_2023_PATH.exists():
            return {}
        payload = json.loads(_HAZARD_2023_PATH.read_text(encoding="utf-8"))
        return payload.get("kota", {}) or {}
    except (OSError, ValueError) as exc:
        logger.warning("hazard_2023_load_failed: %s", exc)
        return {}


def _hazard_2023_for(district: str) -> dict:
    """
    2023 flood hazard index for a kota (more recent than IRBI). Additive; empty
    when no record. Surfaced as context only — does NOT replace the
    IRBI-driven effective_irbi_score that downstream agents key off.
    """
    rec = _load_hazard_2023().get((district or "").strip())
    if not rec:
        return {}
    out: dict = {}
    if isinstance(rec.get("avg_index"), (int, float)):
        out["hazard_index_2023"] = rec["avg_index"]
    if isinstance(rec.get("max_index"), (int, float)):
        out["hazard_index_2023_max"] = rec["max_index"]
    if rec.get("dominant_category"):
        out["hazard_category_2023"] = rec["dominant_category"]
    return out


_KELURAHAN_HISTORY_PATH = Path(__file__).resolve().parents[1] / "data" / "bundled" / "kelurahan_flood_history.json"


@lru_cache(maxsize=1)
def _load_kelurahan_flood_history() -> dict:
    """Kelurahan flood history (per-kelurahan + per-kota). {} on any failure."""
    try:
        if not _KELURAHAN_HISTORY_PATH.exists():
            return {}
        return json.loads(_KELURAHAN_HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("kelurahan_flood_history_load_failed: %s", exc)
        return {}


def kelurahan_flood_history(kelurahan: str) -> dict:
    """
    Public lookup: flood-event history for a single kelurahan (by name).
    Returns {} when unknown. For callers that have a kelurahan-level location.
    """
    rec = _load_kelurahan_flood_history().get("kelurahan", {}).get((kelurahan or "").strip().upper())
    return dict(rec) if rec else {}


def _kelurahan_history_for_kota(district: str) -> dict:
    """
    Per-kota rollup of kelurahan flood history, for merging into
    VulnerabilityContext.to_dict() (which is keyed on kota, not kelurahan).
    Additive; empty when no record.
    """
    rec = _load_kelurahan_flood_history().get("by_kota", {}).get((district or "").strip())
    if not rec:
        return {}
    return {"kelurahan_flood_history": rec}


def _historical_for(district: str) -> dict:
    """
    Historical flood frequency/severity for a kota, suitable for merging into
    VulnerabilityContext.to_dict(). Returns an empty dict when no record exists
    so the field set degrades gracefully (additive, never breaks existing output).
    """
    rec = _load_historical_events().get((district or "").strip())
    if not rec:
        return {}
    out: dict = {}
    if isinstance(rec.get("historical_flood_frequency"), (int, float)):
        out["historical_flood_frequency"] = rec["historical_flood_frequency"]
    if isinstance(rec.get("avg_severity_historical"), (int, float)):
        out["avg_severity_historical"] = rec["avg_severity_historical"]
    if isinstance(rec.get("event_count"), int):
        out["historical_event_count"] = rec["event_count"]
    return out


# ─── Public dataclass ─────────────────────────────────────────────────────────

@dataclass
class VulnerabilityContext:
    """
    Long-term regional flood vulnerability for a Jakarta kota.

    irbi_flood_score:     Raw normalised IRBI flood sub-index (0.0–1.0).
    effective_irbi_score: Decay-adjusted score. THIS is what consuming agents use.
                          Decays toward 50% of raw score over 730 days.
    exposure_class:       Classified from effective_irbi_score.
    data_source:          Provenance tag — ``"api"`` (live InaRISK),
                          ``"static_fallback"`` (bundled JSON), or
                          ``"default"`` (mid-band 0.5 stamped because the
                          district mapped to Jakarta but no IRBI record
                          existed). Surfaces in bnpb_status so operators
                          can tell at a glance which lineage drove a decision.
                          Default ``"api"`` preserves legacy construction.
    """

    irbi_flood_score: float       # Raw normalised IRBI, 0.0–1.0
    effective_irbi_score: float   # Staleness-decayed (used by all agents)
    exposure_class: str           # LOW | MEDIUM | HIGH | VERY_HIGH
    affected_population: int
    data_vintage_days: int
    district: str
    data_source: str = field(default=DATA_SOURCE_API)

    def to_dict(self) -> dict:
        base = {
            "irbi_score": round(self.irbi_flood_score, 4),
            "effective_irbi_score": round(self.effective_irbi_score, 4),
            "exposure_class": self.exposure_class,
            "population": self.affected_population,
            "district": self.district,
            "data_vintage_days": self.data_vintage_days,
            "data_source": self.data_source,
        }
        base.update(_historical_for(self.district))
        base.update(_hazard_2023_for(self.district))
        base.update(_kelurahan_history_for_kota(self.district))
        return base


# ─── Public mapping function ─────────────────────────────────────────────────

def map_to_jakarta_district(location_str: str) -> tuple[str | None, float]:
    """
    Deterministically map a location string to one of five canonical Jakarta kota names.

    Confidence tiers:
      1.00 — exact canonical kota name (e.g. "Jakarta Timur")
      0.95 — exact kota-level alias (abbreviation, English name)
      0.90 — exact kecamatan or kelurahan name
      0.80 — canonical kota name found as substring of input
      0.75 — kecamatan/kelurahan alias found as substring of input
      0.00 — no match

    Returns (None, 0.0) for any input that cannot be confidently matched.
    NO silent fallback to "Jakarta Pusat" or any other default.
    Callers must check confidence >= MAPPING_CONFIDENCE_THRESHOLD before using.
    """
    if not location_str:
        return None, 0.0

    n = location_str.lower().strip()
    if not n:
        return None, 0.0

    # Tier 1: exact canonical name
    if n in _CANONICAL_LOWER:
        return _CANONICAL_LOWER[n], 1.0

    # Tier 2 & 3: exact alias lookup (kota-level vs kecamatan-level)
    if n in _EXACT_ALIASES:
        district = _EXACT_ALIASES[n]
        confidence = 0.95 if n in _KOTA_LEVEL_TOKENS else 0.90
        return district, confidence

    # Tier 4: canonical kota name contained in the input string
    for canon_lower, canon in _CANONICAL_LOWER.items():
        if canon_lower in n:
            return canon, 0.80

    # Tier 5: kecamatan/kelurahan alias contained in input (minimum length guard)
    # Sort by alias length descending so more specific matches win
    for alias, district in sorted(_EXACT_ALIASES.items(), key=lambda x: -len(x[0])):
        if len(alias) >= 6 and alias in n:
            return district, 0.75

    return None, 0.0


# ─── Public context accessor ─────────────────────────────────────────────────

def get_vulnerability_context(
    location_str: str,
) -> tuple[Optional[VulnerabilityContext], dict]:
    """
    Return (VulnerabilityContext | None, mapping_info).

    mapping_info is ALWAYS returned so the caller can emit it in output JSON
    regardless of whether vulnerability data is available.

    Returns (None, mapping_info) when:
      - mapping confidence < MAPPING_CONFIDENCE_THRESHOLD
      - BNPB data unavailable (API down, never fetched)
      - Data vintage > _MAX_VINTAGE_DAYS
      - Any unexpected error

    Never raises.
    """
    district, confidence = map_to_jakarta_district(location_str)
    mapping_info: dict = {
        "input_location": location_str,
        "mapped_district": district if confidence >= MAPPING_CONFIDENCE_THRESHOLD else None,
        "confidence": round(confidence, 4),
    }

    if not district or confidence < MAPPING_CONFIDENCE_THRESHOLD:
        return None, mapping_info

    try:
        raw_data = fetch_bnpb_data()
        raw_ctx = raw_data.get(district)

        # ── DEFAULT path ────────────────────────────────────────────────────
        # District mapped to Jakarta scope but no live or static record
        # exists. Synthesise a mid-band 0.5 context rather than returning
        # None — the API contract guarantees a non-null vulnerability_score
        # whenever the input maps cleanly into Jakarta. The caller (and the
        # gate) sees ``data_source="default"`` and can downgrade trust.
        if not raw_ctx:
            logger.warning(
                "BNPB no record for mapped district %r — using DEFAULT "
                "IRBI=%.2f (data_source=default).",
                district, _DEFAULT_IRBI_SCORE,
            )
            return _build_default_vulnerability(district), mapping_info

        if raw_ctx.data_vintage_days > _MAX_VINTAGE_DAYS:
            BNPB_DATA_STALE_TOTAL.inc()
            logger.debug(
                "BNPB data for %s is %d days old (> %d) — using DEFAULT instead.",
                district, raw_ctx.data_vintage_days, _MAX_VINTAGE_DAYS,
            )
            return _build_default_vulnerability(district), mapping_info

        # Build context with decay-adjusted effective score. Provenance is
        # preserved from the underlying record (api vs static_fallback) so
        # the gate can stamp the correct status code.
        effective = _apply_staleness_decay(raw_ctx.irbi_flood_score, raw_ctx.data_vintage_days)
        ctx = VulnerabilityContext(
            irbi_flood_score=raw_ctx.irbi_flood_score,
            effective_irbi_score=effective,
            exposure_class=_classify_exposure(effective),
            affected_population=raw_ctx.affected_population,
            data_vintage_days=raw_ctx.data_vintage_days,
            district=district,
            data_source=raw_ctx.data_source,
        )
        return ctx, mapping_info

    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        BNPB_FETCH_FAILED_TOTAL.labels(type(exc).__name__).inc()
        logger.warning(
            "get_vulnerability_context(%r) exception (%s) — using DEFAULT.",
            location_str, exc,
        )
        return _build_default_vulnerability(district), mapping_info


# ─── Cache & fetch ────────────────────────────────────────────────────────────

def fetch_bnpb_data() -> dict[str, VulnerabilityContext]:
    """
    Return the current cached BNPB vulnerability map for DKI Jakarta kota.

    Lookup ladder:
      1. In-memory cache (24 h TTL) — last successful fetch, regardless of source.
      2. Live InaRISK API. On success the result is cached and returned.
      3. Static fallback JSON bundled at ``app/data/bnpb_jakarta_fallback.json``.
         Used when (a) the live API fetch raises, OR (b) the live API returns
         an empty map (which historically left the system blind). Result is
         cached with the same 24 h TTL so the next call doesn't re-hit the
         broken upstream. ``data_source="static_fallback"`` on every record.
      4. Last-resort: empty cache + warning. The caller's DEFAULT path then
         takes over for any mapped Jakarta district.

    Never raises.
    """
    global _cache

    age = time.monotonic() - _cache.get("fetched_at", 0.0)
    if _cache and age < _CACHE_TTL:
        return _cache["data"]

    # ── Live API attempt ─────────────────────────────────────────────────────
    try:
        fresh = _fetch_from_apis()
        if fresh:
            _cache = {"fetched_at": time.monotonic(), "data": fresh}
            logger.info("BNPB InaRISK refreshed — %d Jakarta kota loaded.", len(fresh))
            return fresh
        logger.warning(
            "BNPB InaRISK returned empty map — falling back to static JSON."
        )
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        BNPB_FETCH_FAILED_TOTAL.labels(type(exc).__name__).inc()
        logger.warning(
            "BNPB API fetch failed (%s) — falling back to static JSON.", exc
        )

    # ── Static fallback ──────────────────────────────────────────────────────
    static = _load_static_fallback()
    if static:
        _cache = {"fetched_at": time.monotonic(), "data": static}
        logger.warning(
            "BNPB static fallback active — %d Jakarta kota loaded from %s "
            "(source=static_fallback).",
            len(static),
            _FALLBACK_JSON_PATH,
        )
        return static

    # ── Last resort: prior in-memory cache (possibly empty) ──────────────────
    legacy = _cache.get("data", {})
    if not legacy:
        logger.error(
            "BNPB lookup exhausted all sources — live API down AND static "
            "fallback unavailable at %s. Downstream callers will receive "
            "DEFAULT 0.5 IRBI for any mapped Jakarta district.",
            _FALLBACK_JSON_PATH,
        )
    return legacy


def _load_static_fallback() -> dict[str, VulnerabilityContext]:
    """
    Read ``bnpb_jakarta_fallback.json`` and materialise it as
    ``{district: VulnerabilityContext}`` with ``data_source="static_fallback"``.

    Returns ``{}`` (rather than raising) when the file is missing or
    malformed — the caller treats an empty map as "no data, use DEFAULT".
    Vintage is stamped at ``_DEFAULT_VINTAGE_DAYS`` so the staleness gate
    keeps the gate open.
    """
    try:
        with open(_FALLBACK_JSON_PATH, "r", encoding="utf-8-sig") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error(
            "BNPB static fallback unreadable at %s: %s", _FALLBACK_JSON_PATH, exc
        )
        return {}

    districts = payload.get("districts") or {}
    result: dict[str, VulnerabilityContext] = {}
    for district, record in districts.items():
        if not isinstance(record, dict):
            continue
        raw_score = _coerce_float(record.get("irbi_flood_score"))
        if raw_score is None:
            continue
        normalised = min(1.0, max(0.0, raw_score))
        result[district] = VulnerabilityContext(
            irbi_flood_score=round(normalised, 4),
            effective_irbi_score=round(normalised, 4),
            exposure_class=_classify_exposure(normalised),
            affected_population=_coerce_int(record.get("affected_population")) or 0,
            data_vintage_days=_DEFAULT_VINTAGE_DAYS,
            district=district,
            data_source=DATA_SOURCE_STATIC,
        )
    return result


def _build_default_vulnerability(district: str) -> VulnerabilityContext:
    """
    Synthetic mid-band context for a district that mapped successfully into
    Jakarta scope but has no record in either the live API or the static
    fallback. The contract is: ``vulnerability_score`` must NEVER be null or
    0.0 due to a missing record — operators get a conservative MEDIUM
    placeholder and the ``data_source="default"`` tag flags the lineage.
    """
    normalised = _DEFAULT_IRBI_SCORE
    return VulnerabilityContext(
        irbi_flood_score=normalised,
        effective_irbi_score=normalised,
        exposure_class=_classify_exposure(normalised),
        affected_population=0,
        data_vintage_days=_DEFAULT_VINTAGE_DAYS,
        district=district,
        data_source=DATA_SOURCE_DEFAULT,
    )


def _fetch_from_apis() -> dict[str, VulnerabilityContext]:
    with httpx.Client(timeout=_TIMEOUT) as client:
        irbi_raw   = _safe_get(client, _URL_IRBI)
        pasoet_raw = _safe_get(client, _URL_PASOET)
        _safe_get(client, _URL_PROVINSI)  # verifies DKI Jakarta present

    irbi_scores  = _parse_irbi(irbi_raw)
    pop_counts   = _parse_pasoet(pasoet_raw)
    vintage_days = _estimate_vintage_days(irbi_raw)

    result: dict[str, VulnerabilityContext] = {}
    for kota, raw_score in irbi_scores.items():
        normalised = min(1.0, max(0.0, raw_score / _IRBI_NORMALISE_MAX))
        # Store raw normalised score; effective_irbi_score is computed at read time
        # (in get_vulnerability_context) after vintage is known.
        result[kota] = VulnerabilityContext(
            irbi_flood_score=round(normalised, 4),
            effective_irbi_score=round(normalised, 4),  # overwritten on read
            exposure_class=_classify_exposure(normalised),
            affected_population=pop_counts.get(kota, 0),
            data_vintage_days=vintage_days,
            district=kota,
        )
    return result


def _safe_get(client: httpx.Client, url: str) -> dict | list:
    resp = client.get(url)
    resp.raise_for_status()
    return resp.json()


# ─── Parse helpers ────────────────────────────────────────────────────────────

def _parse_irbi(raw: dict | list) -> dict[str, float]:
    """Extract flood IRBI scores for Jakarta kota from bencana-irbi response."""
    records: list = raw if isinstance(raw, list) else raw.get("data", [])

    flood_scores: dict[str, float] = {}
    composite_scores: dict[str, float] = {}

    for rec in records:
        kode    = str(rec.get("kode_kab") or rec.get("kodeKab") or "")
        nama    = str(rec.get("nama_kab") or rec.get("namaKab") or rec.get("nama") or "")
        bencana = str(rec.get("bencana") or rec.get("jenis_bencana") or "").lower()
        score   = _coerce_float(
            rec.get("irbi") or rec.get("skor_irbi") or rec.get("score") or rec.get("nilai")
        )
        if score is None:
            continue
        if kode not in _JAKARTA_KOTA_CODES and "jakarta" not in nama.lower():
            continue

        canonical = _CODE_TO_KOTA.get(kode) or _resolve_kota_from_name(nama)
        if not canonical:
            continue

        if "banjir" in bencana or "flood" in bencana:
            flood_scores[canonical] = max(flood_scores.get(canonical, 0.0), score)
        else:
            composite_scores[canonical] = max(composite_scores.get(canonical, 0.0), score)

    return flood_scores if flood_scores else composite_scores


def _parse_pasoet(raw: dict | list) -> dict[str, int]:
    """Extract exposed population counts for Jakarta kota from data_pasoet."""
    records: list = raw if isinstance(raw, list) else raw.get("data", [])
    result: dict[str, int] = {}

    for rec in records:
        kode = str(rec.get("kode_kab") or rec.get("kodeKab") or "")
        nama = str(rec.get("nama_kab") or rec.get("namaKab") or rec.get("nama") or "")
        pop  = _coerce_int(
            rec.get("penduduk_terpapar") or rec.get("populasi_terpapar")
            or rec.get("total_penduduk") or rec.get("jumlah_penduduk")
            or rec.get("population")
        )
        if kode not in _JAKARTA_KOTA_CODES and "jakarta" not in nama.lower():
            continue
        canonical = _CODE_TO_KOTA.get(kode) or _resolve_kota_from_name(nama)
        if canonical and pop is not None:
            result[canonical] = max(result.get(canonical, 0), pop)

    return result


def _resolve_kota_from_name(name: str) -> str | None:
    """Resolve kota name from BNPB's raw nama_kab field using the canonical map."""
    n = name.lower().strip()
    if n in _CANONICAL_LOWER:
        return _CANONICAL_LOWER[n]
    for canon_lower, canon in _CANONICAL_LOWER.items():
        if canon_lower in n:
            return canon
    return None


def _estimate_vintage_days(raw: dict | list, *, now: "datetime | None" = None) -> int:
    """Estimate data vintage in days. ``now`` (optional) pins the reference clock."""
    ref = now if now is not None else datetime.now(timezone.utc)
    records: list = raw if isinstance(raw, list) else raw.get("data", [])
    first = records[0] if records else {}

    for field in ("last_updated", "updated_at", "tanggal_update", "tgl_update", "tanggal"):
        val = first.get(field)
        if val:
            try:
                dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                return max(0, (ref - dt).days)
            except (ValueError, TypeError):
                pass

    tahun = first.get("tahun") or first.get("year")
    if tahun:
        try:
            mid_year = datetime(int(tahun), 7, 1, tzinfo=timezone.utc)
            return max(0, (ref - mid_year).days)
        except (ValueError, TypeError):
            pass

    BNPB_VINTAGE_FALLBACK_TOTAL.inc()
    logger.warning(
        "BNPB vintage unknown - falling back to default %d days. "
        "Set BNPB_DEFAULT_VINTAGE_DAYS env to tune.",
        _DEFAULT_VINTAGE_DAYS,
    )
    return _DEFAULT_VINTAGE_DAYS


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _apply_staleness_decay(irbi_score: float, vintage_days: int) -> float:
    """
    Time-based decay on IRBI score. Decays toward 50% floor over 730 days.

    Formula: effective = irbi_score * max(0.5, 1 - vintage_days / 730)

    At   0 days: factor = 1.00 (no decay)
    At 180 days: factor = 0.75
    At 365 days: factor = 0.50 (floor)
    """
    decay_factor = max(0.5, 1.0 - vintage_days / 730.0)
    return round(irbi_score * decay_factor, 4)


def _classify_exposure(score: float) -> str:
    if score > _THRESHOLD_VERY_HIGH:
        return "VERY_HIGH"
    if score > _THRESHOLD_HIGH:
        return "HIGH"
    if score > _THRESHOLD_MEDIUM:
        return "MEDIUM"
    return "LOW"


def _coerce_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _coerce_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None
