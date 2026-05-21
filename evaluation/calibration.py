"""
Probability calibration metrics for the flood prediction pipeline.

Computes Brier score, Expected Calibration Error (ECE), and Maximum
Calibration Error (MCE) from a set of predicted probabilities and
binary ground-truth labels.

Note: With only 7 validation scenarios these metrics are directional
indicators, not statistically significant estimates. Interpret with caution.
"""

from __future__ import annotations

import math

from services.decision_engine import write_calibration_cache

_NUM_BINS = 10
_BRIER_EXCELLENT = 0.05
_BRIER_GOOD = 0.10
_BRIER_FAIR = 0.20
_ECE_GOOD = 0.05
_ECE_ACCEPTABLE = 0.10


def _brier_score(probabilities: list[float], binary_labels: list[int]) -> float:
    n = len(probabilities)
    return sum((p - y) ** 2 for p, y in zip(probabilities, binary_labels)) / n


def _calibration_bins(
    probabilities: list[float], binary_labels: list[int], num_bins: int
) -> list[dict]:
    bins: list[dict] = []
    bin_width = 1.0 / num_bins

    for b in range(num_bins):
        lo = b * bin_width
        hi = lo + bin_width
        indices = [
            i for i, p in enumerate(probabilities) if lo <= p < hi
        ]
        # Include p==1.0 in last bin
        if b == num_bins - 1:
            indices = [i for i, p in enumerate(probabilities) if lo <= p <= hi]

        count = len(indices)
        if count == 0:
            bins.append({
                "bin_low": round(lo, 2),
                "bin_high": round(hi, 2),
                "mean_predicted_prob": None,
                "fraction_positive": None,
                "count": 0,
                "gap": None,
            })
            continue

        mean_pred = sum(probabilities[i] for i in indices) / count
        frac_pos = sum(binary_labels[i] for i in indices) / count
        gap = mean_pred - frac_pos

        bins.append({
            "bin_low": round(lo, 2),
            "bin_high": round(hi, 2),
            "mean_predicted_prob": round(mean_pred, 4),
            "fraction_positive": round(frac_pos, 4),
            "count": count,
            "gap": round(gap, 4),
        })

    return bins


def _ece_mce(calibration_bins: list[dict], n_total: int) -> tuple[float, float]:
    ece = 0.0
    mce = 0.0
    for b in calibration_bins:
        if b["count"] == 0 or b["gap"] is None:
            continue
        weight = b["count"] / n_total
        abs_gap = abs(b["gap"])
        ece += weight * abs_gap
        if abs_gap > mce:
            mce = abs_gap
    return round(ece, 4), round(mce, 4)


def _interpret_brier(score: float) -> str:
    if score <= _BRIER_EXCELLENT:
        return f"excellent ({score:.4f} <= {_BRIER_EXCELLENT})"
    if score <= _BRIER_GOOD:
        return f"good ({score:.4f} <= {_BRIER_GOOD})"
    if score <= _BRIER_FAIR:
        return f"fair ({score:.4f} <= {_BRIER_FAIR})"
    return f"poor ({score:.4f} > {_BRIER_FAIR})"


def _interpret_ece(score: float) -> str:
    if score <= _ECE_GOOD:
        return f"well-calibrated ({score:.4f} <= {_ECE_GOOD})"
    if score <= _ECE_ACCEPTABLE:
        return f"acceptable ({score:.4f} <= {_ECE_ACCEPTABLE})"
    return f"miscalibrated ({score:.4f} > {_ECE_ACCEPTABLE})"


def _overconfidence_direction(calibration_bins: list[dict]) -> str:
    filled = [b for b in calibration_bins if b["gap"] is not None]
    if not filled:
        return "insufficient_data"
    pos_gaps = sum(1 for b in filled if b["gap"] > 0.02)
    neg_gaps = sum(1 for b in filled if b["gap"] < -0.02)
    if pos_gaps > neg_gaps:
        return "overconfident"
    if neg_gaps > pos_gaps:
        return "underconfident"
    return "balanced"


def compute_calibration_metrics(
    probabilities: list[float],
    binary_labels: list[int],
) -> dict:
    """
    Compute calibration metrics for a set of flood predictions.

    Args:
        probabilities:  List of predicted flood probabilities (0–1).
        binary_labels:  List of ground-truth labels (1=flood, 0=no-flood).

    Returns:
        Dict with brier_score, ece, mce, direction, interpretations,
        and per-bin calibration_curve. Empty dict if fewer than 2 samples.
    """
    n = len(probabilities)
    if n < 2 or n != len(binary_labels):
        return {
            "error": "insufficient_data",
            "n": n,
            "note": "Need at least 2 samples for calibration metrics.",
        }

    brier = _brier_score(probabilities, binary_labels)
    bins = _calibration_bins(probabilities, binary_labels, _NUM_BINS)
    ece, mce = _ece_mce(bins, n)
    direction = _overconfidence_direction(bins)

    mean_pred = sum(probabilities) / n
    mean_obs = sum(binary_labels) / n

    # Persist ECE so decision_engine can apply a runtime confidence penalty
    # when the model is poorly calibrated (ECE > 0.10 threshold).
    write_calibration_cache(ece=ece, brier=brier, n=n)

    return {
        "n": n,
        "brier_score": round(brier, 4),
        "ece": ece,
        "mce": mce,
        "mean_predicted_probability": round(mean_pred, 4),
        "mean_observed_frequency": round(mean_obs, 4),
        "overconfidence_direction": direction,
        "interpretations": {
            "brier_score": _interpret_brier(brier),
            "ece": _interpret_ece(ece),
            "small_n_warning": (
                f"n={n} — metrics are directional indicators only, "
                "not statistically reliable estimates."
            ) if n < 30 else None,
        },
        "calibration_curve": bins,
    }
