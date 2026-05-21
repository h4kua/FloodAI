"""
historical_evaluator.py — Read-only ground-truth lookup for post-event Jakarta flood data.

ANTI-LEAKAGE CONTRACT
─────────────────────
This service MUST only be called AFTER a risk prediction is complete.
Querying it before or during prediction = DATA LEAKAGE → system design is INVALID.

Safe callers (post-prediction only):
  - ActionAgent           : context enrichment AFTER risk decision
  - historical_demo.py    : offline simulation / evaluation
  - EvaluationAgent       : offline analysis only

FORBIDDEN callers:
  - PerceptionAgent       : pre-prediction signal collection
  - ReasoningAgent        : risk inference

Enforcement: structural isolation (never imported by Perception/Reasoning) plus
the DataLeakageError guard in HistoricalEvaluator.lookup_guarded().
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

_SCENARIOS_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data" / "processed" / "evaluation_scenarios.json"
)

# Severity class thresholds (inclusive lower bound, checked top-down)
_SEVERITY_THRESHOLDS: list[tuple[float, str]] = [
    (0.75, "EXTREME"),
    (0.50, "HIGH"),
    (0.25, "MEDIUM"),
    (0.00, "LOW"),
]


# ── Output type ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class HistoricalContext:
    """
    Ground-truth record for a (date, district) pair.

    Aggregated across all kelurahan sub-events on that day.
    Raw post-event values (water_max_cm, duration_days, evacuees, fatalities)
    are intentionally NOT exposed here — callers see only derived summary fields.
    """
    is_known_event: bool
    historical_severity: float     # 0.0–1.0, max across sub-events
    severity_class: str            # LOW | MEDIUM | HIGH | EXTREME
    event_count: int               # kelurahan-level sub-events on this day
    data_source: str               # "post_event" | "no_record"


class DataLeakageError(RuntimeError):
    """Raised when HistoricalEvaluator is queried before prediction is complete."""


# ── Service ───────────────────────────────────────────────────────────────────

class HistoricalEvaluator:
    """
    Read-only lookup of historical Jakarta flood events (2013-2020).

    Loads evaluation_scenarios.json once and indexes by (date_str, district)
    for O(1) access. All methods are pure — no state is mutated after __init__.

    Usage:
        ev = HistoricalEvaluator()
        ctx = ev.lookup(date(2020, 1, 1), "Jakarta Timur")
        if ctx.is_known_event and ctx.historical_severity >= 0.6:
            ...
    """

    def __init__(self, scenarios_path: Path | str | None = None) -> None:
        path = Path(scenarios_path) if scenarios_path else _SCENARIOS_PATH
        # (date_str, district) -> list of raw scenario records
        self._index: dict[tuple[str, str], list[dict]] = {}

        if path.exists():
            with open(path, encoding="utf-8") as fh:
                records: list[dict] = json.load(fh)
            for rec in records:
                key = (rec.get("date", ""), rec.get("district", ""))
                self._index.setdefault(key, []).append(rec)
            logger.info(
                "HistoricalEvaluator: %d records, %d unique (date, district) pairs",
                len(records),
                len(self._index),
            )
        else:
            logger.warning("HistoricalEvaluator: %s not found — all lookups will return no_record", path)

    # ── Primary lookup ────────────────────────────────────────────────────────

    def lookup(self, query_date: date, district: str) -> HistoricalContext:
        """
        Return ground-truth context for (date, district).

        Returns is_known_event=False when no record exists.
        MUST be called only after ReasoningAgent + EvaluationAgent have completed.
        """
        date_str = query_date.strftime("%Y-%m-%d")
        records = self._index.get((date_str, district), [])

        if not records:
            return HistoricalContext(
                is_known_event=False,
                historical_severity=0.0,
                severity_class="LOW",
                event_count=0,
                data_source="no_record",
            )

        max_severity = max(r.get("severity", 0.0) for r in records)
        return HistoricalContext(
            is_known_event=True,
            historical_severity=round(max_severity, 4),
            severity_class=_classify_severity(max_severity),
            event_count=len(records),
            data_source="post_event",
        )

    def lookup_guarded(
        self,
        query_date: date,
        district: str,
        *,
        prediction_complete: bool,
    ) -> HistoricalContext:
        """
        Programmatic anti-leakage guard.

        Raises DataLeakageError if called before prediction completes.
        Use in any code path where the ordering is not trivially obvious.
        """
        if not prediction_complete:
            raise DataLeakageError(
                "HistoricalEvaluator queried BEFORE prediction is complete — "
                "this is DATA LEAKAGE. ReasoningAgent must run first."
            )
        return self.lookup(query_date, district)

    # ── Utility queries ───────────────────────────────────────────────────────

    def event_dates_for_district(self, district: str) -> list[str]:
        """Sorted list of all date strings with recorded events for a district."""
        return sorted(k[0] for k in self._index if k[1] == district)

    def known_districts(self) -> list[str]:
        """All district names that have at least one event record."""
        return sorted({k[1] for k in self._index})

    def monthly_event_count(self, district: str, year_month: str) -> int:
        """Count event-days for a district matching a YYYY-MM prefix."""
        return sum(
            1 for k in self._index
            if k[1] == district and k[0].startswith(year_month)
        )

    @property
    def total_records(self) -> int:
        """Total kelurahan-level event-day records loaded."""
        return sum(len(v) for v in self._index.values())

    @property
    def total_event_days(self) -> int:
        """Total unique (date, district) pairs with events."""
        return len(self._index)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _classify_severity(s: float) -> str:
    for threshold, cls in _SEVERITY_THRESHOLDS:
        if s >= threshold:
            return cls
    return "LOW"


# ── Module-level singleton ────────────────────────────────────────────────────

_default_evaluator: HistoricalEvaluator | None = None


def get_evaluator() -> HistoricalEvaluator:
    """Return the module-level shared HistoricalEvaluator (lazy init on first call)."""
    global _default_evaluator
    if _default_evaluator is None:
        _default_evaluator = HistoricalEvaluator()
    return _default_evaluator
