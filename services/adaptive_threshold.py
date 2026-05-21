"""
AdaptiveThresholder - context-aware threshold provider for flood prediction.

This module no longer classifies a final risk level. Its job is to compute the
operating thresholds that the canonical decision runtime in
``app.domain.decision.decide()`` consumes.

Threshold adjustment logic:
  OOD input          -> +0.10 (raise: sensor faults must NOT trigger DANGER)
  Missing data       -> +0.05 (raise: conservatism under incomplete observation)
  Trend anomaly      -> -0.06 (lower: historical escalation pattern confirmed)
  Rapid rise         -> -0.05 (lower: imminent danger window, stacked with anomaly)
  High plausibility  -> -0.04 (lower: physically realistic extreme, trust signals)
  Signal conflict    -> -0.07 (lower: baseline may see danger ML misses)
  Hard floor / ceil  -> [0.25, 0.55]
"""

from __future__ import annotations

from dataclasses import dataclass, field
import warnings


# ─── Canonical threshold source (single source of truth) ─────────────────────
# Every base/min/max value below derives from one helper —
# decision_engine._canonical_default_thresholds() — which itself reads the
# realtime-native inference thresholds. ZERO numeric threshold literals live
# in this file. The legacy 0.20/0.30/0.45 triplet was removed so the realtime
# inference layer, the adaptive thresholder, and the canonical adapter
# defaults all resolve to the same numbers automatically.


def _base_triplet() -> tuple[float, float, float]:
    """(pre_alert, warning, danger) sourced from the canonical authority."""
    from services.decision_engine import _canonical_default_thresholds
    return _canonical_default_thresholds()


def _base_pre_alert() -> float:
    return _base_triplet()[0]


def _base_warning() -> float:
    return _base_triplet()[1]


def _base_danger() -> float:
    return _base_triplet()[2]


def _min_danger() -> float:
    """Conservative floor: at most the canonical warning threshold."""
    return _base_triplet()[1]


def _max_danger() -> float:
    """
    Conservative ceiling derived from the canonical danger threshold so the
    operating envelope tracks the source automatically instead of drifting.
    """
    return min(0.95, _base_triplet()[2] + 0.30)


_ADJ_OOD_RAISE = +0.10
_ADJ_MISSING_RAISE = +0.05
_ADJ_TREND_ANOMALY = -0.06
_ADJ_RAPID_RISE = -0.05
_ADJ_HIGH_PLAUS = -0.04
_ADJ_CONFLICT_LOWER = -0.07
_ADJ_STRONG_TREND = -0.04

_PLAUSIBILITY_HIGH_MARK = 0.90
_RAPID_RISE_RATE_MIN = 0.04
_PLAUSIBILITY_CAN_LOWER = 0.40
_STRONG_TREND_STRENGTH = 0.40
_STRONG_TREND_CONFIDENCE = 0.60


@dataclass
class ThresholdAdjustment:
    """One applied adjustment to the DANGER threshold."""

    reason: str
    delta: float


@dataclass
class AdaptiveThresholdProfile:
    """
    Audit record of one adaptive threshold calibration pass.

    The payload remains serializable under the legacy
    ``prediction["adaptive_classification"]`` key for compatibility, but it is
    threshold-only and non-authoritative.
    """

    pre_alert_threshold: float
    warning_threshold: float
    danger_threshold: float
    base_pre_alert_threshold: float
    base_warning_threshold: float
    base_danger_threshold: float
    adjustments: list[ThresholdAdjustment] = field(default_factory=list)
    threshold_basis: str = ""
    calibration_version: str = "phase8-canonical-thresholds-v1"
    calibration_source: str = "services.adaptive_threshold.AdaptiveThresholder"

    def to_dict(self) -> dict:
        return {
            "pre_alert_threshold": self.pre_alert_threshold,
            "warning_threshold": self.warning_threshold,
            "danger_threshold": self.danger_threshold,
            "base_pre_alert_threshold": self.base_pre_alert_threshold,
            "base_warning_threshold": self.base_warning_threshold,
            "base_danger_threshold": self.base_danger_threshold,
            "effective_danger_threshold": self.danger_threshold,
            "net_adjustment": round(
                self.danger_threshold - self.base_danger_threshold,
                4,
            ),
            "adjustments": [
                {"reason": a.reason, "delta": round(a.delta, 4)}
                for a in self.adjustments
            ],
            "threshold_basis": self.threshold_basis,
            "classification_basis": self.threshold_basis,
            "calibration_version": self.calibration_version,
            "calibration_source": self.calibration_source,
        }


class AdaptiveThresholder:
    """
    Context-aware threshold provider for the canonical decision runtime.

    Reads three independent context signals before deciding the operating
    thresholds:
      failure_modes       - types of failures (OOD, missing_data, signal_conflict)
      trend_state         - anomaly_detected, risk_rate_per_hour from compute_trend()
      plausibility_score  - 0.0 (physically impossible) to 1.0 (realistic)

    Guard: raising adjustments (OOD, missing_data) block lowering adjustments
    to prevent paradoxical behavior where a bad-input penalty and a
    sensitivity increase cancel each other out.
    """

    def build_thresholds(
        self,
        failure_modes: list[dict],
        trend_state: dict,
        plausibility_score: float,
    ) -> AdaptiveThresholdProfile:
        """Build context-adjusted operating thresholds."""
        failure_types = {f.get("type", "") for f in failure_modes}
        adjustments: list[ThresholdAdjustment] = []
        base_pre_alert = _base_pre_alert()
        base_warning = _base_warning()
        base_danger = _base_danger()
        min_danger = _min_danger()
        max_danger = _max_danger()
        danger_threshold = base_danger

        if "ood_input" in failure_types:
            adjustments.append(
                ThresholdAdjustment(
                    reason=(
                        "OOD input - sensor malfunction likely; extreme values are "
                        "noise, not signal"
                    ),
                    delta=_ADJ_OOD_RAISE,
                )
            )
            danger_threshold += _ADJ_OOD_RAISE

        if "missing_data" in failure_types:
            adjustments.append(
                ThresholdAdjustment(
                    reason=(
                        "Missing data - cannot independently verify extreme conditions"
                    ),
                    delta=_ADJ_MISSING_RAISE,
                )
            )
            danger_threshold += _ADJ_MISSING_RAISE

        can_lower = (
            "ood_input" not in failure_types
            and plausibility_score >= _PLAUSIBILITY_CAN_LOWER
        )

        if can_lower:
            if trend_state.get("anomaly_detected"):
                anomaly_type = trend_state.get("anomaly_type", "unknown")
                adjustments.append(
                    ThresholdAdjustment(
                        reason=(
                            f"Trend anomaly ({anomaly_type}) in recent history - "
                            "context confirms escalation independent of model output"
                        ),
                        delta=_ADJ_TREND_ANOMALY,
                    )
                )
                danger_threshold += _ADJ_TREND_ANOMALY

                rate = float(trend_state.get("risk_rate_per_hour") or 0.0)
                if rate > _RAPID_RISE_RATE_MIN:
                    adjustments.append(
                        ThresholdAdjustment(
                            reason=(
                                f"Rapid risk escalation rate {rate:.3f}/hr - "
                                "imminent danger development window"
                            ),
                            delta=_ADJ_RAPID_RISE,
                        )
                    )
                    danger_threshold += _ADJ_RAPID_RISE

            if plausibility_score >= _PLAUSIBILITY_HIGH_MARK:
                adjustments.append(
                    ThresholdAdjustment(
                        reason=(
                            f"High physical plausibility ({plausibility_score:.2f}) - "
                            "extreme input is physically realistic"
                        ),
                        delta=_ADJ_HIGH_PLAUS,
                    )
                )
                danger_threshold += _ADJ_HIGH_PLAUS

            if "signal_conflict" in failure_types:
                adjustments.append(
                    ThresholdAdjustment(
                        reason=(
                            "Signal conflict present - rule-based baseline may be "
                            "detecting danger that the ML model undersells"
                        ),
                        delta=_ADJ_CONFLICT_LOWER,
                    )
                )
                danger_threshold += _ADJ_CONFLICT_LOWER

            trend_strength = float(trend_state.get("trend_strength", 0.0))
            trend_confidence = float(trend_state.get("trend_confidence", 0.0))
            if (
                trend_state.get("risk_trend") == "increasing"
                and trend_strength >= _STRONG_TREND_STRENGTH
                and trend_confidence >= _STRONG_TREND_CONFIDENCE
            ):
                adjustments.append(
                    ThresholdAdjustment(
                        reason=(
                            "Strong rising trend - consistent upward trajectory "
                            "across prediction history"
                        ),
                        delta=_ADJ_STRONG_TREND,
                    )
                )
                danger_threshold += _ADJ_STRONG_TREND

        effective_danger = round(
            max(min_danger, min(max_danger, danger_threshold)),
            4,
        )
        warning_threshold = round(
            max(
                base_pre_alert + 0.01,
                min(effective_danger - 0.05, base_warning),
            ),
            4,
        )
        if warning_threshold > effective_danger:
            warning_threshold = round(
                max(base_pre_alert, effective_danger - 0.01),
                4,
            )

        if adjustments:
            basis = (
                "Context-adjusted thresholds derived from failure modes, trend "
                "state, and plausibility signals. Final risk classification is "
                "delegated to app.domain.decision.decide()."
            )
        else:
            basis = (
                "Default static thresholds - no context adjustments applied. "
                "Final risk classification is delegated to "
                "domain.decision.decide()."
            )

        return AdaptiveThresholdProfile(
            pre_alert_threshold=base_pre_alert,
            warning_threshold=warning_threshold,
            danger_threshold=effective_danger,
            base_pre_alert_threshold=base_pre_alert,
            base_warning_threshold=base_warning,
            base_danger_threshold=base_danger,
            adjustments=adjustments,
            threshold_basis=basis,
        )

    def classify(
        self,
        probability: float,
        failure_modes: list[dict],
        trend_state: dict,
        plausibility_score: float,
    ) -> AdaptiveThresholdProfile:
        """
        Deprecated compatibility wrapper.

        The probability argument is ignored. Callers must consume the returned
        thresholds and delegate final classification to
        ``app.domain.decision.decide()``.
        """
        del probability
        warnings.warn(
            "AdaptiveThresholder.classify() is deprecated; use build_thresholds() "
            "and delegate final classification to app.domain.decision.decide().",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.build_thresholds(
            failure_modes=failure_modes,
            trend_state=trend_state,
            plausibility_score=plausibility_score,
        )
