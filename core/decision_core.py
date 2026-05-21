"""
DecisionCore — Signal aggregation layer.

This module is a STRUCTURED SIGNAL AGGREGATOR, NOT a decision engine.

Design invariants (must never be violated):
  1. DecisionCore MUST NOT determine risk_level.
  2. DecisionCore MUST NOT combine signals into a single authoritative score.
  3. BNPB (vulnerability_score) MUST NOT affect risk_level.
  4. exposure_score MUST NOT affect risk_level.
  5. uncertainty_score may influence EvaluationAgent._requires_manual_review().
     hazard_score feeds ONLY into informational consistency trace notes.
     Neither hazard_score nor any composite score determines risk_level.
  6. EvaluationAgent remains the ONLY decision authority.

composite_signal_strength = 0.6*hazard + 0.2*exposure + 0.2*vulnerability
  -> EXPLAINABILITY AND RANKING ONLY — never used as a decision threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.hydrology_analyzer import HydrologyAssessment
    from services.trust_model import TrustBreakdown

# ─── Constants ────────────────────────────────────────────────────────────────

# SOLE BEHAVIORAL HOOK in this module: when uncertainty_score exceeds this
# threshold, EvaluationAgent._requires_manual_review() returns True.
# This is the ONLY output of DecisionCore that influences pipeline behavior.
# It does NOT affect risk_level, system_status, or probability.
UNCERTAINTY_MANUAL_REVIEW_THRESHOLD = 0.65

# Composite weights — EXPLAINABILITY ONLY, never used in decision logic.
_W_HAZARD = 0.6
_W_EXPOSURE = 0.2
_W_VULNERABILITY = 0.2

# Normalisation denominators for physical signals
_RAINFALL_SATURATION_MM = 50.0   # 50 mm/3h -> score 1.0
_RAINFALL_RATE_SATURATION = 20.0  # 20 mm/h -> score 1.0
_WL_SIAGA1_CM = 950.0            # 950 cm Katulampa ~ SIAGA 1 threshold


# ─── RiskState ────────────────────────────────────────────────────────────────


@dataclass
class RiskState:
    """
    Structured signal state produced by DecisionCore.build_state().

    Semantics:
      hazard_score        — 0-1, physical flood hazard intensity.
                            The ONLY dimension that may feed into decision logic
                            (via consistency checks in EvaluationAgent).
      exposure_score      — 0-1, population/asset exposure to flood impact.
                            FOR EXPLAINABILITY ONLY.
      vulnerability_score — 0-1, structural vulnerability from BNPB InaRISK.
                            FOR EXPLAINABILITY ONLY.
      uncertainty_score   — 0-1, (1 - composite_trust); higher = less trustworthy.
      override_flag       — True when SIAGA1 physical condition was detected.
      override_reason     — Human-readable reason; empty string when False.
      composite_signal_strength — 0.6*hazard + 0.2*exposure + 0.2*vulnerability.
                                  FOR EXPLAINABILITY ONLY.
      dominant_factor     — name of the highest-scoring dimension.
    """

    hazard_score: float = 0.0
    exposure_score: float = 0.0
    vulnerability_score: float = 0.0
    uncertainty_score: float = 0.0
    override_flag: bool = False
    override_reason: str = ""
    composite_signal_strength: float = 0.0
    dominant_factor: str = "hazard"

    def to_dict(self) -> dict:
        return {
            "hazard_score": round(self.hazard_score, 4),
            "exposure_score": round(self.exposure_score, 4),
            "vulnerability_score": round(self.vulnerability_score, 4),
            "uncertainty_score": round(self.uncertainty_score, 4),
            "override_flag": self.override_flag,
            "override_reason": self.override_reason,
            "composite_signal_strength": round(self.composite_signal_strength, 4),
            "dominant_factor": self.dominant_factor,
        }


# ─── DecisionCore ─────────────────────────────────────────────────────────────


# Architectural separation: DecisionCore is the feature computation layer;
# EvaluationAgent is the decision layer. Moving these computations into
# EvaluationAgent would violate modular separation and increase coupling —
# EvaluationAgent would own both signal normalisation and decision authority.
# DecisionCore feeds: uncertainty_score → _requires_manual_review() condition 5;
# RiskState → ActionAgent explainability output and consistency trace notes.
class DecisionCore:
    """
    NON-AUTHORITATIVE — explainability decoration only.

    Signal aggregation layer — NOT a decision maker. Final risk_level and
    system_status are determined exclusively by app.domain.decision.decide().

    build_state() normalises raw sensor/model signals into a RiskState.
    Callers use RiskState for:
      - Explainability output in the final decision report
      - Consistency notes (high hazard + SAFE -> informational trace entry, no mutation)
      - Uncertainty-based manual review flagging via uncertainty_score
        (the ONLY behavioral output — see UNCERTAINTY_MANUAL_REVIEW_THRESHOLD)

    Called by EvaluationAgent after the decision engine runs, so override_trace
    is available. Produces the non-authoritative risk_state attached to EvaluationResult.

    All parameters are keyword-only to prevent positional misuse.
    """

    def build_state(
        self,
        *,
        model_prob: float,
        model_confidence: float,
        features: dict[str, Any],
        signals: dict[str, Any],
        diagnostics: dict[str, Any],
        trust_breakdown: "TrustBreakdown | None" = None,
        vulnerability_context: Any = None,
        hydrology_assessment: "HydrologyAssessment | None" = None,
        override_trace: dict[str, Any] | None = None,
    ) -> RiskState:
        """
        Normalise raw signals into a RiskState for explainability and checks.

        Produces four independent dimension scores in [0.0, 1.0]:
          hazard_score       — 0.5*ML_prob + 0.3*hydrology + 0.2*rainfall
          exposure_score     — 0.6*water_level_ratio + 0.4*population_proxy
          vulnerability_score — IRBI flood score from BNPB
          uncertainty_score  — 1 - composite_trust (or 1 - model_confidence)

        SIAGA1 override: when hydrology_assessment, override_trace, or signals
        indicate SIAGA1, hazard_score is forced to 1.0 and override_flag=True.
        This is INFORMATIONAL in RiskState — the actual SIAGA1 decision
        escalation lives in decision_engine.py and is not duplicated here.
        """
        is_siaga1, override_reason = self._detect_siaga1(
            hydrology_assessment, override_trace, signals, features
        )

        hazard_score = self._compute_hazard(
            model_prob=model_prob,
            signals=signals,
            features=features,
            hydrology_assessment=hydrology_assessment,
            is_siaga1=is_siaga1,
        )
        exposure_score = self._compute_exposure(features, signals, vulnerability_context)
        vulnerability_score = self._compute_vulnerability(vulnerability_context)
        uncertainty_score = self._compute_uncertainty(model_confidence, trust_breakdown)

        composite = (
            _W_HAZARD * hazard_score
            + _W_EXPOSURE * exposure_score
            + _W_VULNERABILITY * vulnerability_score
        )

        scores = {
            "hazard": hazard_score,
            "exposure": exposure_score,
            "vulnerability": vulnerability_score,
            "uncertainty": uncertainty_score,
        }
        dominant_factor = max(scores, key=lambda k: scores[k])

        return RiskState(
            hazard_score=round(hazard_score, 4),
            exposure_score=round(exposure_score, 4),
            vulnerability_score=round(vulnerability_score, 4),
            uncertainty_score=round(uncertainty_score, 4),
            override_flag=is_siaga1,
            override_reason=override_reason,
            composite_signal_strength=round(composite, 4),
            dominant_factor=dominant_factor,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _detect_siaga1(
        self,
        hydrology_assessment: Any,
        override_trace: dict | None,
        signals: dict,
        features: dict,
    ) -> tuple[bool, str]:
        """Return (is_siaga1, override_reason) from multiple evidence sources."""
        override_applied = False
        if override_trace:
            override_applied = bool(
                override_trace.get("triggered")
                or override_trace.get("physical_override_applied", False)
            )
        if override_applied:
            return True, override_trace.get("reason", "critical water level")

        if hydrology_assessment is not None:
            siaga = getattr(hydrology_assessment, "siaga_level", None)
            if siaga is None:
                siaga = getattr(hydrology_assessment, "dominant_siaga_level", None)
            siaga_text = str(siaga).upper().replace("_", "").replace("-", "")
            if siaga in (1, "1") or siaga_text == "SIAGA1":
                return True, "critical water level — SIAGA1 threshold breached"
            wl_status = str(getattr(hydrology_assessment, "water_level_status", "")).upper()
            wl_status = wl_status.replace("_", "").replace("-", "")
            if wl_status == "SIAGA1":
                return True, "critical water level — SIAGA1 threshold breached"

        if signals.get("siaga_1") or signals.get("siaga1"):
            return True, "critical water level — SIAGA1 threshold breached"

        return False, ""

    def _compute_hazard(
        self,
        *,
        model_prob: float,
        signals: dict,
        features: dict,
        hydrology_assessment: Any,
        is_siaga1: bool,
    ) -> float:
        """hazard = 0.5*ML_prob + 0.3*hydrology_signal + 0.2*rainfall_signal."""
        if is_siaga1:
            return 1.0
        ml_component = model_prob * 0.5
        hydro_component = self._hydrology_signal(hydrology_assessment, signals, features) * 0.3
        rainfall_component = self._rainfall_signal(features, signals) * 0.2
        return min(1.0, ml_component + hydro_component + rainfall_component)

    def _hydrology_signal(
        self, hydrology_assessment: Any, signals: dict, features: dict
    ) -> float:
        """Normalise hydrology risk to [0.0, 1.0]."""
        if hydrology_assessment is not None:
            risk_score = getattr(hydrology_assessment, "risk_score", None)
            if risk_score is not None:
                return float(min(1.0, max(0.0, risk_score)))
            siaga_map = {4: 0.2, 3: 0.5, 2: 0.8, 1: 1.0}
            siaga = getattr(hydrology_assessment, "siaga_level", None)
            if siaga in siaga_map:
                return siaga_map[siaga]

        if signals.get("water_level_critical"):
            return 1.0
        if signals.get("water_level_high") or signals.get("rapid_rise"):
            return 0.7
        if signals.get("water_level_elevated"):
            return 0.4

        wl_ratio = float(features.get("water_level_ratio", 0.0))
        return min(1.0, wl_ratio) if wl_ratio > 0.0 else 0.0

    def _rainfall_signal(self, features: dict, signals: dict) -> float:
        """Normalise rainfall signal to [0.0, 1.0]."""
        if signals.get("extreme_rainfall"):
            return 1.0
        if signals.get("high_rainfall"):
            return 0.8
        if signals.get("moderate_rainfall"):
            return 0.5

        acc_3h = float(
            features.get("rainfall_acc_3h", features.get("rainfall_acc_3h_mm", 0.0))
        )
        if acc_3h > 0:
            return min(1.0, acc_3h / _RAINFALL_SATURATION_MM)

        rate = float(
            features.get("rainfall_intensity_mmh", features.get("rainfall_rate_mmh", 0.0))
        )
        return min(1.0, rate / _RAINFALL_RATE_SATURATION)

    def _compute_exposure(
        self, features: dict, signals: dict, vulnerability_context: Any
    ) -> float:
        """
        Exposure score (EXPLAINABILITY ONLY).
        = 0.6 * water_level_contribution + 0.4 * population_proxy
        """
        wl_ratio = float(features.get("water_level_ratio", 0.0))
        if wl_ratio == 0.0:
            katulampa_cm = float(features.get("water_level_katulampa_cm", 0.0))
            if katulampa_cm > 0:
                wl_ratio = min(1.0, katulampa_cm / _WL_SIAGA1_CM)
        wl_exposure = min(1.0, wl_ratio) * 0.6

        if vulnerability_context is not None:
            cls = str(getattr(vulnerability_context, "exposure_class", "LOW")).upper()
            cls_map = {
                "VERY_HIGH": 1.0, "HIGH": 0.75, "MEDIUM": 0.5,
                "LOW": 0.25, "VERY_LOW": 0.1,
            }
            pop_score = cls_map.get(cls, 0.25)
        else:
            pop_score = 0.25  # neutral default when no BNPB data
        pop_exposure = pop_score * 0.4

        return min(1.0, wl_exposure + pop_exposure)

    def _compute_vulnerability(self, vulnerability_context: Any) -> float:
        """
        Vulnerability score (EXPLAINABILITY ONLY).
        Maps BNPB InaRISK IRBI flood score to [0.0, 1.0].
        """
        if vulnerability_context is None:
            return 0.0
        irbi = getattr(vulnerability_context, "effective_irbi_score", None)
        if irbi is not None:
            return float(min(1.0, max(0.0, irbi)))
        cls = str(getattr(vulnerability_context, "exposure_class", "LOW")).upper()
        cls_map = {
            "VERY_HIGH": 0.9, "HIGH": 0.7, "MEDIUM": 0.5,
            "LOW": 0.3, "VERY_LOW": 0.1,
        }
        return cls_map.get(cls, 0.3)

    def _compute_uncertainty(
        self, model_confidence: float, trust_breakdown: Any
    ) -> float:
        """
        Uncertainty = 1 - composite_trust when trust breakdown is available,
        else 1 - model_confidence.
        """
        if trust_breakdown is not None:
            composite = getattr(trust_breakdown, "composite_trust", None)
            if composite is not None:
                return float(min(1.0, max(0.0, 1.0 - composite)))
        return float(min(1.0, max(0.0, 1.0 - model_confidence)))
