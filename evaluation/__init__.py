"""
Evaluation Module — scenario harness + classification metrics.

Phase 7 cleanup: the adversarial-testing framework was quarantined to
``_deprecated/evaluation__adversarial_framework.py`` because its trace markers
(``[L0-DATA] -> [L1-PHYSICAL] -> ...``) and parallel ``RISK_TIER`` vocabulary
diverged from canonical ``app.contracts.vocabulary`` and the
``Decision.decision_trace`` shape produced by ``app.domain.decide``. Anyone
who needs adversarial robustness evaluation should rebuild it on top of
canonical vocabulary; the legacy implementation is preserved on disk for
reference but produces misleading numbers and MUST NOT be reused as-is.

Exports:
  - SCENARIO_LABELS, ScenarioLabel: scenario reference labels
  - compute_classification_metrics, aggregate_evaluation_report: metrics
  - run_scenarios: scenario harness entry point
"""

from evaluation.metrics import (
    SCENARIO_LABELS,
    ScenarioLabel,
    compute_classification_metrics,
    aggregate_evaluation_report,
)

from evaluation.scenario_runner import run_scenarios

__all__ = [
    "SCENARIO_LABELS",
    "ScenarioLabel",
    "compute_classification_metrics",
    "aggregate_evaluation_report",
    "run_scenarios",
]