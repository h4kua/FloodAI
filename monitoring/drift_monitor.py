"""
Drift monitor for the realtime-native flood prediction model.

Purpose
-------
Decide WHEN to retrain — never on a calendar. Pulls a recent window of
observed feature distributions, compares each feature column against the
training-time baseline via a two-sample Kolmogorov–Smirnov test, and emits
a structured ``DriftReport`` containing per-feature p-values, KS statistics,
sample sizes, and a single boolean ``retrain_recommended``.

Retrain rule
------------
Retrain is recommended when at least ``min_drift_features`` (default 2)
features have a KS p-value strictly below ``p_threshold`` (default 0.05).
Both are env-tunable so SRE can dial sensitivity without code changes.

Sources of truth
----------------
* Recent observations  → ``realtime_feature_history.csv`` (the only persisted
                         per-call feature log; written by feature_builder).
                         Today this file only carries 3 columns
                         (``timestamp``, ``rainfall_mm``, ``water_level_ratio``)
                         — see the TODO comment in ``load_recent_window``.
                         The monitor handles any subset of columns and the
                         "≥2 drifting features" rule still works.
* Training baseline    → ``data/processed/realtime_native_training_bootstrap.csv``
                         (or any DataFrame supplied by the caller).

Output
------
* JSON report written to ``artifacts/reports/drift/drift_<ISO timestamp>.json``
  on every run, including feature-level detail.
* Prometheus counters ``flood_drift_features_total`` /
  ``flood_drift_retrain_triggered_total`` (best-effort; falls through
  when the observability module is unavailable).
* When ``retrain_recommended=True`` AND ``--apply`` is passed on the CLI,
  invokes ``scripts/retrain_bundle.py --re-export-only`` via subprocess
  using ``sys.executable`` so the manifest's ``runtime_versions`` block
  is captured against the same interpreter the API will serve under.

CLI
---
    python -m app.monitoring.drift_monitor               # dry-run, prints JSON
    python -m app.monitoring.drift_monitor --apply       # trigger retrain if drift
    python -m app.monitoring.drift_monitor --window 500 --p-threshold 0.01
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from scipy import stats

from realtime_native.feature_builder import (
    REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH,
    REALTIME_NATIVE_FEATURES,
    REALTIME_NATIVE_HISTORY_PATH,
)
from utils.paths import REPORTS_DIR


logger = logging.getLogger(__name__)


# ─── Tunables (env-overridable) ───────────────────────────────────────────────

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _p_threshold() -> float:
    return _env_float("FLOOD_DRIFT_P_THRESHOLD", 0.05)


def _min_drift_features() -> int:
    return max(1, _env_int("FLOOD_DRIFT_MIN_FEATURES", 2))


def _recent_window_rows() -> int:
    return max(20, _env_int("FLOOD_DRIFT_WINDOW_ROWS", 200))


def _baseline_sample_rows() -> int:
    return max(20, _env_int("FLOOD_DRIFT_BASELINE_ROWS", 2000))


# Report destination — operators can grep this directory for drift history.
_DRIFT_REPORTS_DIR = REPORTS_DIR / "drift"


# ─── Result types ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FeatureDrift:
    """KS-test outcome for one feature column."""

    feature: str
    ks_statistic: float       # 0.0 (identical) ... 1.0 (disjoint)
    p_value: float            # null hypothesis: same distribution
    recent_n: int
    baseline_n: int
    recent_mean: float | None
    baseline_mean: float | None
    drifted: bool             # p_value < threshold


@dataclass
class DriftReport:
    """Full drift assessment for a single check cycle."""

    generated_at: str
    p_threshold: float
    min_drift_features: int
    recent_window_rows: int
    baseline_rows: int
    features_evaluated: list[str]
    features: list[FeatureDrift] = field(default_factory=list)
    drift_count: int = 0
    retrain_recommended: bool = False
    retrain_reason: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        # Round floats to 6 dp for stable JSON / hash comparisons.
        for f in d["features"]:
            for key in ("ks_statistic", "p_value", "recent_mean", "baseline_mean"):
                val = f.get(key)
                if isinstance(val, float):
                    f[key] = round(val, 6)
        return d


# ─── Loaders ──────────────────────────────────────────────────────────────────


def load_recent_window(
    *,
    history_path: Path | str = REALTIME_NATIVE_HISTORY_PATH,
    limit: int | None = None,
) -> pd.DataFrame:
    """
    Read the most-recent ``limit`` rows from the realtime feature history CSV.

    TODO (scope-out): the history CSV currently only persists a 3-column
    subset of the 16 realtime-native features (timestamp, rainfall_mm,
    water_level_ratio). When the H6 "move realtime_feature_history to
    Postgres" audit fix lands, point this loader at the new table and the
    KS-test will run on the full 16-feature space automatically — no
    drift_monitor change required.
    """
    path = Path(history_path)
    if not path.exists():
        logger.warning("drift: feature history not found at %s", path)
        return pd.DataFrame()

    df = pd.read_csv(path)
    n = limit if limit is not None else _recent_window_rows()
    if n > 0 and len(df) > n:
        df = df.tail(n).reset_index(drop=True)
    return df


def _resolve_baseline_path(dataset_path: Path | str | None) -> Path:
    """
    Resolution order for the drift baseline:
      1. Caller-supplied ``dataset_path``.
      2. ``model_card.training_dataset`` — what the LIVE model was actually
         fit on. After an incremental retrain this points at the merged
         (bootstrap + pseudo-labels) CSV so drift detection compares
         against the model's true reference distribution, not the
         long-superseded bootstrap-only dataset.
      3. ``REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH`` — cold-start fallback.
    """
    if dataset_path is not None:
        return Path(dataset_path)
    try:
        from realtime_native.bundle import load_runtime_bundle  # local import
        mc_path = load_runtime_bundle().model_card.get("training_dataset")
        if mc_path:
            resolved = Path(str(mc_path))
            if resolved.exists():
                return resolved
            logger.warning(
                "drift: model_card.training_dataset=%s missing on disk — "
                "falling back to bootstrap path.", mc_path,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("drift: model_card lookup skipped (%s) — using bootstrap.", exc)
    return Path(REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH)


def load_baseline(
    *,
    dataset_path: Path | str | None = None,
    max_rows: int | None = None,
    random_state: int = 42,
) -> pd.DataFrame:
    """Read (and optionally subsample) the training-time baseline."""
    path = _resolve_baseline_path(dataset_path)
    if not path.exists():
        logger.warning("drift: baseline dataset not found at %s", path)
        return pd.DataFrame()

    df = pd.read_csv(path)
    cap = max_rows if max_rows is not None else _baseline_sample_rows()
    if cap > 0 and len(df) > cap:
        df = df.sample(n=cap, random_state=random_state).reset_index(drop=True)
    return df


# ─── KS-test core ─────────────────────────────────────────────────────────────


def compute_drift_report(
    recent: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    features: Iterable[str] | None = None,
    p_threshold: float | None = None,
    min_drift_features: int | None = None,
    now: datetime | None = None,
) -> DriftReport:
    """
    Run a two-sample KS test per feature and return a structured report.

    Features that exist in only one frame are skipped (and noted in the
    server log) rather than silently failing. NaN/Inf values are dropped
    per-column before testing.
    """
    p_thr = float(p_threshold if p_threshold is not None else _p_threshold())
    min_drift = int(min_drift_features if min_drift_features is not None else _min_drift_features())
    ref_now = now if now is not None else datetime.now(timezone.utc)

    if features is None:
        # Intersect the configured canonical feature set with whatever both
        # frames actually carry — robust to partial-feature history logs.
        configured = set(REALTIME_NATIVE_FEATURES)
        common = configured & set(recent.columns) & set(baseline.columns)
        feature_list = sorted(common)
    else:
        feature_list = [f for f in features if f in recent.columns and f in baseline.columns]

    report = DriftReport(
        generated_at=ref_now.isoformat(),
        p_threshold=p_thr,
        min_drift_features=min_drift,
        recent_window_rows=int(len(recent)),
        baseline_rows=int(len(baseline)),
        features_evaluated=feature_list,
    )

    if not feature_list or recent.empty or baseline.empty:
        report.retrain_reason = (
            "no_overlapping_features_or_empty_window — skipped (recent_rows="
            f"{len(recent)}, baseline_rows={len(baseline)}, "
            f"overlap={len(feature_list)})"
        )
        return report

    drifted_count = 0
    for feat in feature_list:
        r_series = pd.to_numeric(recent[feat], errors="coerce").dropna()
        b_series = pd.to_numeric(baseline[feat], errors="coerce").dropna()
        r_clean = r_series[np.isfinite(r_series)]
        b_clean = b_series[np.isfinite(b_series)]
        if len(r_clean) < 5 or len(b_clean) < 5:
            # Too few samples for KS to be meaningful — report explicitly.
            report.features.append(FeatureDrift(
                feature=feat,
                ks_statistic=0.0,
                p_value=1.0,
                recent_n=int(len(r_clean)),
                baseline_n=int(len(b_clean)),
                recent_mean=float(r_clean.mean()) if len(r_clean) else None,
                baseline_mean=float(b_clean.mean()) if len(b_clean) else None,
                drifted=False,
            ))
            continue

        ks_stat, p_value = stats.ks_2samp(r_clean.values, b_clean.values)
        drifted = bool(p_value < p_thr)
        if drifted:
            drifted_count += 1
        report.features.append(FeatureDrift(
            feature=feat,
            ks_statistic=float(ks_stat),
            p_value=float(p_value),
            recent_n=int(len(r_clean)),
            baseline_n=int(len(b_clean)),
            recent_mean=float(r_clean.mean()),
            baseline_mean=float(b_clean.mean()),
            drifted=drifted,
        ))

    report.drift_count = drifted_count
    report.retrain_recommended = drifted_count >= min_drift
    drifted_features = [f.feature for f in report.features if f.drifted]
    if report.retrain_recommended:
        report.retrain_reason = (
            f"{drifted_count} features drifted (p<{p_thr}): "
            + ", ".join(drifted_features)
        )
        for f in report.features:
            if f.drifted:
                logger.warning(
                    "drift: feature=%s ks=%.4f p=%.4g recent_mean=%s baseline_mean=%s",
                    f.feature, f.ks_statistic, f.p_value,
                    f.recent_mean, f.baseline_mean,
                )
    else:
        report.retrain_reason = (
            f"{drifted_count} features drifted (need >= {min_drift}); "
            "no retrain recommended"
        )

    return report


# ─── Persistence + observability ──────────────────────────────────────────────


def persist_report(report: DriftReport, *, out_dir: Path | str = _DRIFT_REPORTS_DIR) -> Path:
    """Write the report to ``artifacts/reports/drift/drift_<ts>.json``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    # Filename uses a filesystem-safe variant of the ISO timestamp.
    safe_ts = report.generated_at.replace(":", "").replace("+", "_")
    path = out / f"drift_{safe_ts}.json"
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(report.to_dict(), fh, indent=2)
    os.replace(tmp, path)
    return path


def _emit_metrics(report: DriftReport) -> None:
    """Best-effort Prometheus emission; never raises."""
    try:
        from api.observability import (  # type: ignore[import-not-found]
            DRIFT_FEATURES_TOTAL,
            DRIFT_RETRAIN_TRIGGERED_TOTAL,
        )
    except ImportError:
        return
    try:
        DRIFT_FEATURES_TOTAL.inc(report.drift_count)
        if report.retrain_recommended:
            DRIFT_RETRAIN_TRIGGERED_TOTAL.inc()
    except Exception:  # noqa: BLE001
        logger.debug("drift: metric emission skipped", exc_info=True)


# ─── Trigger ──────────────────────────────────────────────────────────────────


def trigger_retrain_subprocess(
    *,
    re_export_only: bool = True,
    extra_args: Iterable[str] = (),
) -> subprocess.CompletedProcess:
    """
    Spawn ``scripts/retrain_bundle.py`` using ``sys.executable`` so the
    manifest's ``runtime_versions`` block reflects the same interpreter
    serving inference. ``--re-export-only`` is the default for safety
    (full retrain is opt-in via ``re_export_only=False``).
    """
    script = Path(__file__).resolve().parents[1] / "scripts" / "retrain_bundle.py"
    cmd = [sys.executable, str(script)]
    if re_export_only:
        cmd.append("--re-export-only")
    cmd.extend(extra_args)
    logger.info("drift: invoking retrain subprocess: %s", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


# ─── Orchestrator ─────────────────────────────────────────────────────────────


def evaluate_drift_and_maybe_retrain(
    *,
    apply: bool = False,
    p_threshold: float | None = None,
    min_drift_features: int | None = None,
    window: int | None = None,
    baseline_rows: int | None = None,
) -> dict:
    """
    End-to-end check used by both CLI and any scheduled job.

    Returns a dict containing:
      - ``report``: the DriftReport serialised via ``to_dict()``
      - ``report_path``: filesystem path of the persisted JSON
      - ``retrain_invoked``: bool — True only when ``apply=True`` AND drift fired
      - ``retrain_result``: subprocess outcome dict (or None)
    """
    recent = load_recent_window(limit=window)
    baseline = load_baseline(max_rows=baseline_rows)

    report = compute_drift_report(
        recent,
        baseline,
        p_threshold=p_threshold,
        min_drift_features=min_drift_features,
    )
    report_path = persist_report(report)
    _emit_metrics(report)
    logger.info(
        "drift: drift_count=%d recommended=%s report=%s",
        report.drift_count, report.retrain_recommended, report_path,
    )

    retrain_invoked = False
    retrain_result: dict | None = None
    if apply and report.retrain_recommended:
        cp = trigger_retrain_subprocess(re_export_only=True)
        retrain_invoked = True
        retrain_result = {
            "returncode": cp.returncode,
            "stdout_tail": (cp.stdout or "")[-500:],
            "stderr_tail": (cp.stderr or "")[-500:],
        }
        if cp.returncode != 0:
            logger.error(
                "drift: retrain subprocess failed rc=%d stderr=%s",
                cp.returncode, retrain_result["stderr_tail"],
            )

    return {
        "report": report.to_dict(),
        "report_path": str(report_path),
        "retrain_invoked": retrain_invoked,
        "retrain_result": retrain_result,
    }


# ─── CLI ──────────────────────────────────────────────────────────────────────


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Drift-detection check for the realtime-native flood model.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Invoke scripts/retrain_bundle.py --re-export-only when drift is "
            "detected. Default is dry-run: report only, no side effects."
        ),
    )
    parser.add_argument(
        "--window", type=int, default=None,
        help="Override FLOOD_DRIFT_WINDOW_ROWS (recent rows from the history log).",
    )
    parser.add_argument(
        "--baseline-rows", type=int, default=None,
        help="Override FLOOD_DRIFT_BASELINE_ROWS (sample size from training data).",
    )
    parser.add_argument(
        "--p-threshold", type=float, default=None,
        help="Override FLOOD_DRIFT_P_THRESHOLD (default 0.05).",
    )
    parser.add_argument(
        "--min-features", type=int, default=None,
        help="Override FLOOD_DRIFT_MIN_FEATURES (default 2).",
    )
    return parser


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _build_arg_parser().parse_args()
    outcome = evaluate_drift_and_maybe_retrain(
        apply=args.apply,
        p_threshold=args.p_threshold,
        min_drift_features=args.min_features,
        window=args.window,
        baseline_rows=args.baseline_rows,
    )
    # Stream a one-line summary first, then the full report (for piping into jq).
    print(json.dumps({
        "drift_count":          outcome["report"]["drift_count"],
        "retrain_recommended":  outcome["report"]["retrain_recommended"],
        "retrain_invoked":      outcome["retrain_invoked"],
        "report_path":          outcome["report_path"],
    }, indent=2))
    return 0 if (not outcome["retrain_invoked"] or
                 (outcome["retrain_result"] or {}).get("returncode", 0) == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
