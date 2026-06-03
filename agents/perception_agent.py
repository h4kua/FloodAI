"""
PerceptionAgent — Stage 1 of the agentic flood decision pipeline.

Responsibility: parse and validate the raw snapshot dict, assess data
freshness and structural completeness, and identify which signal categories
(rainfall, hydrology, BMKG) are actually present in the current observation.

Explicitly does NOT make risk decisions — that belongs to ReasoningAgent.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("flood.perception")

# Configurable via SENSOR_MAX_DELTA_CM env var; per-station override via
# station record field "max_delta_cm". Default 500 cm covers the realistic
# worst-case Ciliwung flood surge (Manggarai highest-ever ≈ 1050 cm, rising
# from ~200 cm baseline in ≈ 6 readings = ~140 cm/step; 500 cm is >3× that).
_SENSOR_MAX_DELTA_DEFAULT: float = float(os.getenv("SENSOR_MAX_DELTA_CM", "500"))
# Fraction of total stations that must be anomalous before the HIGH mass-failure
# gate fires. Below this, anomalies are filtered quietly with sensor_anomalies list.
_MASS_FAULT_FRACTION: float = 0.50
# Maximum age (hours) of a station's `tanggal` relative to snapshot `fetched_at_utc`
# before the station is excluded from ratio/hydrology calculations.
_STATION_STALE_HOURS: float = float(os.getenv("STATION_STALE_HOURS", "2"))

from services.bmkg_filter import filter_jakarta_bmkg_alerts
from services.bnpb_context import VulnerabilityContext, get_vulnerability_context

# Jakarta + Jabodetabek tokens used to filter raw bmkg_feed items when
# bmkg_alerts (CAP detail) is empty. Intentionally broader than the strict
# Jakarta-only set so upstream watershed signals are not silently dropped.
_JABODETABEK_TOKENS = (
    "jakarta", "dki jakarta", "jabodetabek", "bodetabek",
    "depok", "tangerang", "bekasi", "bogor",
    "katulampa", "ciliwung", "citarum",
)


def _feed_items_to_alerts(feed_items: list) -> list:
    """
    Convert bmkg_feed RSS items to minimal alert dicts when bmkg_alerts is empty.

    Only items whose title or description contains a Jakarta/Jabodetabek token
    are included so we don't treat national alerts as local risk signals.
    """
    result = []
    for item in feed_items:
        text = " ".join([
            str(item.get("title") or ""),
            str(item.get("description") or ""),
        ]).lower()
        if not any(tok in text for tok in _JABODETABEK_TOKENS):
            continue
        result.append({
            "identifier": item.get("alert_code", ""),
            "alert_code": item.get("alert_code", ""),
            "event": str(item.get("title") or "").split("—")[0].strip(),
            "urgency": "Unknown",
            "severity": "Moderate",
            "certainty": "Possible",
            "effective": item.get("pub_date", ""),
            "expires": "",
            "headline": str(item.get("title") or ""),
            "description": str(item.get("description") or ""),
            "instruction": "",
            "area_desc": str(item.get("title") or "").split("—")[-1].strip(),
            "polygons": [],
            "parameters": {},
            "_source": "bmkg_feed_fallback",
        })
    return result
from services.dem_elevation import (
    classify_flood_zone,
    estimate_flow_direction,
    get_elevation,
    get_elevation_context,
)
from services.hydrology_analyzer import HydrologyAssessment, analyze_hydrology
from services.plausibility_check import score_plausibility


@dataclass
class PerceptionResult:
    """Structured output of PerceptionAgent. Passed directly to ReasoningAgent."""

    snapshot: dict
    openweather: dict
    poskobanjir: list
    bmkg_alerts: list
    # Minutes since snapshot was fetched; -1.0 if timestamp absent or unparseable.
    data_freshness_minutes: float
    # Fraction of expected top-level sections present (0.0–1.0).
    snapshot_completeness: float
    # Which signal categories are detectable from the current snapshot.
    signal_presence: dict
    # Raw scalars extracted directly from snapshot (before the feature builder runs).
    raw_features: dict
    # Physical plausibility score 0.0–1.0 from score_plausibility().
    plausibility_score: float = 1.0
    plausibility: dict = field(default_factory=dict)
    # Station IDs quarantined for physically impossible water-level readings.
    # These stations are removed from poskobanjir before feature extraction.
    quarantined_stations: list[str] = field(default_factory=list)
    # Stations filtered due to an implausible water-level delta (rate-of-change
    # spike). Each entry: {"station", "reason", "value", "current_level", "previous_level"}.
    sensor_anomalies: list[dict] = field(default_factory=list)
    # Stations whose `tanggal` is > STATION_STALE_HOURS old relative to snapshot
    # `fetched_at_utc`. Excluded from water level ratio and hydrology calculations.
    # Each entry: {"station", "reason", "tanggal", "age_hours"}.
    stale_stations: list[dict] = field(default_factory=list)
    # Per-station hydrology assessment from analyze_hydrology().
    hydrology_assessment: HydrologyAssessment = field(default_factory=HydrologyAssessment)
    # Non-blocking issues noted during parsing. No risk decisions made here.
    perception_warnings: list[str] = field(default_factory=list)
    # Long-term regional vulnerability from BNPB InaRISK (NOT real-time).
    # None when BNPB API is unavailable or district cannot be matched.
    # MUST NOT influence probability or risk_level — affects only manual_review
    # threshold and recommended_action priority.
    vulnerability_context: Optional[VulnerabilityContext] = field(default=None)
    # District mapping audit trail from get_vulnerability_context().
    # Always present so ActionAgent can surface it regardless of whether
    # vulnerability_context is None (failed/low-confidence mapping).
    mapping_info: dict = field(default_factory=dict)
    # Additive DEM enrichment. Empty when coordinates are absent or the DEM is unavailable.
    elevation: dict = field(default_factory=dict)


class PerceptionAgent:
    """
    Stage 1: Perception.

    Parses the raw JSON snapshot and answers three structural questions:
      1. How fresh is this data?
      2. Which required sections are present?
      3. Which physical signal categories are detectable?

    All output is factual and descriptive — no risk judgement is made here.
    """

    _EXPECTED_SECTIONS = ("fetched_at_utc", "openweather", "poskobanjir", "bmkg_alerts")
    _NORMALIZED_DELTA_KEYS = ("water_level_delta", "water_level_delta_cur")
    _PREVIOUS_LEVEL_KEYS = (
        "tinggi_air_sebelumnya",   # primary Indonesian field name from Posko XML
        "previous_tinggi_air",
        "tinggi_air_prev",
        "tinggi_air_previous",
        "previous_height_cm",
        "prev_height_cm",
        "height_cm_prev",
    )
    _HISTORY_KEYS = ("ketinggian", "height_cm_history", "water_level_history")

    def run(self, snapshot: dict, *, now: "datetime | None" = None) -> PerceptionResult:
        warnings: list[str] = []

        openweather = snapshot.get("openweather") or {}
        poskobanjir = snapshot.get("poskobanjir") or []
        bmkg_alerts = filter_jakarta_bmkg_alerts(snapshot.get("bmkg_alerts") or [])

        # When bmkg_alerts is empty (CAP detail fetch failed or no active alerts),
        # fall back to bmkg_feed RSS items filtered for Jakarta/Jabodetabek relevance
        # and use them as a lightweight risk signal via basic alert structs.
        if not bmkg_alerts:
            bmkg_alerts = _feed_items_to_alerts(snapshot.get("bmkg_feed") or [])

        freshness = self._compute_freshness(snapshot, warnings, now=now)
        completeness = self._compute_completeness(snapshot)

        # Surface absent hydrology early so operators correlate a downstream
        # STALE/DEGRADED TMA response with a snapshot that already carries no
        # station data. PerceptionAgent itself does not call the TMA scraper —
        # RoutingAgent does — but seeing both signals together in the response
        # cuts diagnosis time in half during an incident.
        if not poskobanjir:
            warnings.append(
                "Snapshot contains no poskobanjir water-level records — hydrology "
                "signals will rely on cached or external TMA data if available."
            )

        # Score plausibility on the raw snapshot first so we can identify and
        # quarantine stations before any feature extraction reads their values.
        plausibility_dict  = score_plausibility(snapshot)
        plausibility_float = float(plausibility_dict.get("plausibility_score", 1.0))

        quarantined = plausibility_dict.get("quarantined_stations") or []
        if quarantined:
            logger.warning(
                "quarantine_stations count=%d ids=%s",
                len(quarantined), quarantined,
            )
            warnings.append(
                f"Station(s) {quarantined} quarantined: water_level exceeds physical bound. "
                "Excluded from feature extraction."
            )
            poskobanjir = [s for s in poskobanjir if s.get("id") not in quarantined]

        # ── Delta-rate anomaly detection ─────────────────────────────────────
        # Run on the post-physical-bounds list so already-quarantined stations
        # are not double-counted. Uses per-station "max_delta_cm" if present,
        # falling back to the deployment-wide env-var default.
        delta_anomalies = self._detect_delta_anomalies(poskobanjir, _SENSOR_MAX_DELTA_DEFAULT)
        if delta_anomalies:
            anomalous_ids = [a["station"] for a in delta_anomalies]
            logger.warning(
                "delta_anomaly_stations count=%d ids=%s",
                len(anomalous_ids), anomalous_ids,
            )
            warnings.append(
                f"Station(s) {anomalous_ids} excluded: water_level delta exceeds threshold. "
                "Filtered before feature extraction."
            )
            poskobanjir = [s for s in poskobanjir if s.get("id") not in anomalous_ids]

        # ── Stale station detection ───────────────────────────────────────────
        # Reference: snapshot fetched_at_utc (not system clock) for reproducibility.
        # Stations with tanggal > STATION_STALE_HOURS old are excluded from
        # water level ratio and hydrology calculations but surfaced explicitly.
        _fetched_at_raw = snapshot.get("fetched_at_utc")
        _reference_dt: datetime | None = None
        try:
            _reference_dt = datetime.fromisoformat(
                str(_fetched_at_raw).replace("Z", "+00:00")
            )
        except (ValueError, TypeError):
            pass

        stale_stations: list[dict] = []
        if _reference_dt is not None:
            stale_stations = self._detect_stale_stations(poskobanjir, _reference_dt)
        if stale_stations:
            stale_names = {s["station"] for s in stale_stations}
            logger.warning(
                "stale_stations count=%d names=%s",
                len(stale_names), sorted(stale_names),
            )
            warnings.append(
                f"Station(s) {sorted(stale_names)} excluded: tanggal > {_STATION_STALE_HOURS:.0f}h old "
                "relative to fetched_at_utc. Excluded from water level and hydrology calculations."
            )
            # Match by station name (all name-field variants) so ALL stale stations
            # are excluded — not just ones where id happens to equal the name string.
            def _station_name(s: dict) -> str:
                return (
                    s.get("nama_pintu_air") or s.get("nama") or
                    s.get("name") or s.get("wilayah") or
                    s.get("id") or ""
                )
            poskobanjir = [s for s in poskobanjir if _station_name(s) not in stale_names]

        # >50% gate — all fault types combined against the original raw count.
        total_raw = len(snapshot.get("poskobanjir") or [])
        total_faulted = len(quarantined) + len(delta_anomalies) + len(stale_stations)
        if total_raw > 0 and (total_faulted / total_raw) > _MASS_FAULT_FRACTION:
            logger.error(
                "mass_sensor_failure total=%d faulted=%d fraction=%.2f",
                total_raw, total_faulted, total_faulted / total_raw,
            )
            warnings.append(
                f"MASS_SENSOR_FAILURE: {total_faulted}/{total_raw} stations faulted "
                f"({100 * total_faulted / total_raw:.0f}%) — confidence degraded."
            )

        signal_presence = self._assess_signal_presence(openweather, poskobanjir, bmkg_alerts)
        raw_features = self._extract_raw_features(openweather, poskobanjir, bmkg_alerts)
        water_level_delta = self._extract_water_level_delta(snapshot, poskobanjir)
        hydrology = analyze_hydrology(
            poskobanjir,
            water_level_delta=water_level_delta,
        )

        # BNPB InaRISK vulnerability context — silently None on any failure.
        #
        # Resolution policy (priority order, the FIRST surface to produce a
        # non-empty district_query wins):
        #
        #   (a) User-supplied location string (kota OR kecamatan alias) →
        #       trust verbatim and let ``get_vulnerability_context`` resolve
        #       kota-level aliases internally. This guarantees user intent
        #       is never overridden by GPS-derived coord lookups.
        #
        #   (b) Coord-based kecamatan_by_coords on the openweather centroid
        #       — used only when (a) is absent, OR purely as ENRICHMENT
        #       metadata (kecamatan name + idkec) that never changes the
        #       kabkot the IRBI gate keys off.
        #
        #   (c) Openweather "name" — legacy fallback.
        from services.bnpb_jakarta_mapper import (
            get_kecamatan,
            get_kecamatan_by_coords,
        )

        raw_location = (
            snapshot.get("location_raw")
            if isinstance(snapshot.get("location_raw"), str)
            else snapshot.get("location")
        )

        # The authoritative kabkot-resolution string: trust the user when
        # supplied; otherwise leave empty and let the coord/name fallbacks
        # populate it.
        district_query: str = ""
        if isinstance(raw_location, str) and raw_location.strip():
            district_query = raw_location

        # Kecamatan-level lookup: try the user string first (matches
        # "Penjaringan", "kec. tanjung priok", etc.). When the user input
        # is a kota, ``get_kecamatan`` returns None — we then fall back
        # to GPS-coord nearest-neighbour for enrichment ONLY.
        kecamatan_record: dict | None = None
        if isinstance(raw_location, str) and raw_location.strip():
            kecamatan_record = get_kecamatan(raw_location)
        coord = openweather.get("coord") or {}
        try:
            _lat: float | None = float(coord.get("lat"))
            _lon: float | None = float(coord.get("lon"))
        except (TypeError, ValueError):
            _lat = None
            _lon = None

        if kecamatan_record is None and _lat is not None and _lon is not None:
            kecamatan_record = get_kecamatan_by_coords(_lat, _lon)

        # ONLY fill district_query from a kecamatan record when the user
        # gave us nothing AND the kecamatan was resolved from a user-typed
        # string (not from a GPS coord — coord-derived kabkot must not
        # override a user-supplied kota).
        if not district_query and kecamatan_record is not None and \
                kecamatan_record.get("distance_km") is None:
            kabkot_raw = str(kecamatan_record.get("kabkot") or "").strip()
            if kabkot_raw and kabkot_raw != "UNKNOWN":
                district_query = " ".join(p.capitalize() for p in kabkot_raw.split())
        if not district_query:
            district_query = (openweather.get("name") if openweather else "") or ""

        # get_vulnerability_context always returns a 2-tuple:
        #   (VulnerabilityContext | None, mapping_info dict)
        # It handles kota AND kecamatan aliases internally — so passing
        # the raw user string is sufficient.
        vuln_context, mapping_info = get_vulnerability_context(str(district_query))
        if kecamatan_record is not None:
            # Surface the kecamatan-level lineage for operator audit. Kept
            # under a separate key so existing consumers of mapping_info
            # don't see a shape change.
            mapping_info["kecamatan"] = {
                "name":        kecamatan_record.get("name"),
                "kabkot":      kecamatan_record.get("kabkot"),
                "idkec":       kecamatan_record.get("idkec"),
                "distance_km": kecamatan_record.get("distance_km"),
                "source":      "bnpb_jakarta_mapper",
            }

        elevation_payload: dict = {}
        if _lat is not None and _lon is not None:
            elev = get_elevation(_lat, _lon)
            elev_ctx = get_elevation_context(_lat, _lon)
            flow = estimate_flow_direction(_lat, _lon)
            elevation_payload = {
                "elevation_m": elev["elevation_m"],
                "flood_zone": classify_flood_zone(elev["elevation_m"])
                if elev["elevation_m"] is not None else "unknown",
                "is_below_sea_level": elev["is_below_sea_level"],
                "is_local_depression": elev_ctx["is_local_minimum"],
                "depression_score": elev_ctx["depression_score"],
                "flow_direction": flow.get("flow_direction", "unknown"),
                "flow_confidence": flow.get("confidence", "low"),
                "source": "DEMNAS_BIG_8m",
            }

        # Flood-prone zone enrichment (additive; never affects risk_level or
        # probability). Spatial proximity to a recorded flood-prone point.
        if _lat is not None and _lon is not None:
            try:
                from services.flood_prone_locator import (
                    in_flood_prone_zone,
                    nearest_prone_point,
                )

                in_zone = in_flood_prone_zone(_lat, _lon)
                signal_presence["in_flood_prone_zone"] = in_zone
                nearest = nearest_prone_point(_lat, _lon)
                if nearest:
                    mapping_info["flood_prone"] = {"in_zone": in_zone, **nearest}
            except Exception:  # noqa: BLE001 — enrichment is best-effort
                pass

            # Drainage-infrastructure context: nearby pump houses. Higher pump
            # density is a mitigating drainage factor (advisory only).
            try:
                from services.pump_locator import (
                    get_nearest_pump_houses,
                    pump_drainage_capacity,
                )

                drainage = pump_drainage_capacity(_lat, _lon)
                signal_presence["pump_drainage_score"] = drainage.get("drainage_score", 0.0)
                mapping_info["pump_drainage_capacity"] = drainage
                pumps = get_nearest_pump_houses(_lat, _lon, limit=3)
                if pumps:
                    mapping_info["nearest_pump_houses"] = pumps
            except Exception:  # noqa: BLE001 — enrichment is best-effort
                pass

        # River-overflow flood zone (name-based; works without coordinates).
        try:
            from services.flood_prone_locator import river_overflow_zone

            kec_name = kecamatan_record.get("name") if kecamatan_record else None
            if kec_name:
                ro = river_overflow_zone(kecamatan=kec_name)
                signal_presence["in_river_overflow_zone"] = ro["in_river_overflow_zone"]
                if ro["in_river_overflow_zone"]:
                    mapping_info["river_overflow"] = ro
        except Exception:  # noqa: BLE001 — enrichment is best-effort
            pass

        return PerceptionResult(
            snapshot=snapshot,
            openweather=openweather,
            poskobanjir=poskobanjir,
            bmkg_alerts=bmkg_alerts,
            data_freshness_minutes=freshness,
            snapshot_completeness=completeness,
            signal_presence=signal_presence,
            raw_features=raw_features,
            plausibility_score=plausibility_float,
            plausibility=plausibility_dict,
            quarantined_stations=quarantined,
            sensor_anomalies=delta_anomalies,
            stale_stations=stale_stations,
            hydrology_assessment=hydrology,
            perception_warnings=warnings,
            vulnerability_context=vuln_context,
            mapping_info=mapping_info,
            elevation=elevation_payload,
        )

    def _compute_freshness(
        self,
        snapshot: dict,
        warnings: list[str],
        *,
        now: "datetime | None" = None,
    ) -> float:
        """
        Compute freshness against the orchestrator's pinned clock when supplied.
        Falls back to wall-clock only when called outside a pipeline run.
        """
        ref = now if now is not None else datetime.now(timezone.utc)
        fetched_at = snapshot.get("fetched_at_utc")
        if not fetched_at:
            warnings.append("Missing fetched_at_utc — data freshness unknown.")
            return -1.0
        try:
            dt = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
            return (ref - dt).total_seconds() / 60.0
        except (ValueError, TypeError):
            warnings.append(f"Cannot parse fetched_at_utc: {fetched_at!r}")
            return -1.0

    def _compute_completeness(self, snapshot: dict) -> float:
        present = sum(1 for s in self._EXPECTED_SECTIONS if snapshot.get(s) is not None)
        return round(present / len(self._EXPECTED_SECTIONS), 4)

    def _assess_signal_presence(self, ow: dict, posko: list, bmkg: list) -> dict:
        main = ow.get("main") or {}
        rain = ow.get("rain") or {}
        return {
            "has_temperature": bool(main.get("temp")),
            "has_humidity": bool(main.get("humidity")),
            "has_rainfall_1h": "1h" in rain,
            "has_rainfall_3h": "3h" in rain,
            "has_water_levels": len(posko) > 0,
            "has_bmkg_alerts": len(bmkg) > 0,
            "posko_record_count": len(posko),
            "bmkg_alert_count": len(bmkg),
        }

    def _extract_raw_features(self, ow: dict, posko: list, bmkg: list) -> dict:
        main = ow.get("main") or {}
        rain = ow.get("rain") or {}
        return {
            "temperature_c": main.get("temp"),
            "humidity_pct": main.get("humidity"),
            "rainfall_1h_mm": rain.get("1h", 0.0),
            "rainfall_3h_mm": rain.get("3h", 0.0),
            "bmkg_alert_count": len(bmkg),
            "water_level_records": len(posko),
        }

    def _extract_water_level_delta(self, snapshot: dict, posko: list) -> float | None:
        for container in (snapshot, snapshot.get("diagnostics") or {}):
            if not isinstance(container, dict):
                continue
            for key in self._NORMALIZED_DELTA_KEYS:
                delta = self._safe_float(container.get(key))
                if delta is not None:
                    return delta

        deltas = [
            delta
            for delta in (self._station_water_level_delta(record) for record in posko)
            if delta is not None
        ]
        if not deltas:
            return None
        return round(max(deltas), 4)

    def _station_water_level_delta(self, record: dict) -> float | None:
        for key in self._NORMALIZED_DELTA_KEYS:
            delta = self._safe_float(record.get(key))
            if delta is not None:
                return delta

        current_level = self._safe_float(record.get("tinggi_air"))
        if current_level is None:
            return None

        previous_level = None
        for key in self._PREVIOUS_LEVEL_KEYS:
            previous_level = self._safe_float(record.get(key))
            if previous_level is not None:
                break

        if previous_level is None:
            history = self._extract_numeric_series(record)
            if len(history) >= 2:
                previous_level = history[-2]
                current_level = history[-1]

        if previous_level is None:
            return None

        reference = self._reference_threshold(record)
        if reference is None or reference <= 0:
            return None

        return round((current_level - previous_level) / reference, 4)

    def _extract_numeric_series(self, record: dict) -> list[float]:
        for key in self._HISTORY_KEYS:
            raw = record.get(key)
            if raw in ("", None):
                continue
            values = raw if isinstance(raw, list) else str(raw).split(",")
            series: list[float] = []
            for value in values:
                parsed = self._safe_float(value)
                if parsed is not None:
                    series.append(parsed)
            if len(series) >= 2:
                return series
        return []

    def _reference_threshold(self, record: dict) -> float | None:
        thresholds = [
            value
            for value in (
                self._safe_float(record.get("siaga1")),
                self._safe_float(record.get("siaga2")),
                self._safe_float(record.get("siaga3")),
                self._safe_float(record.get("siaga4")),
            )
            if value is not None and value > 0
        ]
        if not thresholds:
            return None
        return max(thresholds)

    def _detect_delta_anomalies(
        self,
        stations: list[dict],
        max_delta_default: float,
    ) -> list[dict]:
        """
        Flag stations whose water level jumped by more than max_delta_default cm
        (or the station-level override "max_delta_cm") since the previous reading.

        Stations with no previous reading are skipped — missing history is never
        a false positive. Returns a list of anomaly dicts, one per flagged station.
        """
        anomalies: list[dict] = []
        for s in stations:
            current = self._safe_float(s.get("tinggi_air"))
            if current is None:
                continue
            threshold = float(s.get("max_delta_cm") or max_delta_default)

            previous: float | None = None
            for key in self._PREVIOUS_LEVEL_KEYS:
                previous = self._safe_float(s.get(key))
                if previous is not None:
                    break

            if previous is None:
                history = self._extract_numeric_series(s)
                if len(history) >= 2:
                    previous = history[-2]

            if previous is None:
                continue  # no baseline — cannot assert anomaly

            delta = abs(current - previous)
            if delta > threshold:
                anomalies.append(
                    {
                        "station": s.get("id", "?"),
                        "reason": (
                            f"water_level_delta {delta:.0f} cm exceeds "
                            f"threshold {threshold:.0f} cm"
                        ),
                        "value": delta,
                        "current_level": current,
                        "previous_level": previous,
                    }
                )
        return anomalies

    def _detect_stale_stations(
        self,
        stations: list[dict],
        reference_dt: datetime,
    ) -> list[dict]:
        """
        Return stations whose `tanggal` timestamp is older than _STATION_STALE_HOURS
        relative to `reference_dt` (snapshot fetched_at_utc).

        Stations with no parseable tanggal are skipped — absence of a timestamp
        is not treated as staleness to avoid false positives on partial records.
        """
        stale: list[dict] = []
        for s in stations:
            tanggal = s.get("tanggal")
            if not tanggal:
                continue
            try:
                station_dt = datetime.fromisoformat(
                    str(tanggal).replace("Z", "+00:00")
                )
                if station_dt.tzinfo is None:
                    station_dt = station_dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            ref = reference_dt if reference_dt.tzinfo else reference_dt.replace(tzinfo=timezone.utc)
            age_hours = (ref - station_dt).total_seconds() / 3600.0
            if age_hours > _STATION_STALE_HOURS:
                station_name = (
                    s.get("nama_pintu_air") or s.get("name") or
                    s.get("wilayah") or s.get("id") or "unknown"
                )
                stale.append({
                    "station": station_name,
                    "reason": (
                        f"tanggal {age_hours:.1f}h old "
                        f"(threshold {_STATION_STALE_HOURS:.1f}h)"
                    ),
                    "tanggal": str(tanggal),
                    "age_hours": round(age_hours, 2),
                    "status": str(s.get("status_siaga") or s.get("status") or ""),
                    # Include current water level so action generator can cite it
                    "tinggi_air": s.get("tinggi_air"),
                    "siaga1": s.get("siaga1"),
                    "_raw_record": s,
                })
        return stale

    def _safe_float(self, value: object) -> float | None:
        try:
            if value in ("", None):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
