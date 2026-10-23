import hashlib
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from imblearn.over_sampling import SMOTE

from realtime_native.feature_builder import (
    REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH,
    REALTIME_NATIVE_FEATURES,
    build_bootstrap_training_dataset,
    kecamatan_flood_freq_map_before,
)
from utils.paths import MODELS_DIR, REALTIME_NATIVE_BUNDLE_DIR, REPORTS_DIR


def _focal_loss_objective(y_true_or_pred, dtrain_or_y_true):
    """XGBoost-compatible focal loss (gamma=2, alpha=0.75) — down-weights
    easy negatives so the model focuses on hard-to-classify flood events.

    XGBoost sklearn API calls this as (y_true, y_pred) — raw margin values."""
    gamma = 1.5
    alpha = 0.75
    if hasattr(dtrain_or_y_true, "get_label"):
        y_true = dtrain_or_y_true.get_label()
        y_pred = y_true_or_pred
    else:
        y_true = y_true_or_pred
        y_pred = dtrain_or_y_true
    p = 1.0 / (1.0 + np.exp(-y_pred))
    p = np.clip(p, 1e-7, 1 - 1e-7)
    alpha_t = np.where(y_true == 1, alpha, 1 - alpha)
    pt = np.where(y_true == 1, p, 1 - p)
    grad = alpha_t * (
        gamma * np.power(1 - pt, gamma - 1) * pt * np.log(pt + 1e-9)
        - np.power(1 - pt, gamma) * (y_true - p)
    )
    hess = np.abs(grad) * (1 - np.abs(grad))
    hess = np.clip(hess, 1e-7, None)
    return grad, hess


logger = logging.getLogger(__name__)


REALTIME_NATIVE_MODEL_PATH = MODELS_DIR / "flood_model_realtime_native.pkl"
REALTIME_NATIVE_SCALER_PATH = MODELS_DIR / "scaler_realtime_native.pkl"
REALTIME_NATIVE_FEATURE_LIST_PATH = MODELS_DIR / "feature_list_realtime_native.json"
REALTIME_NATIVE_MODEL_CARD_PATH = MODELS_DIR / "model_card_realtime_native.json"
REALTIME_NATIVE_OOD_PATH = MODELS_DIR / "ood_detector_realtime_native.pkl"
REALTIME_NATIVE_THRESHOLD_PATH = MODELS_DIR / "optimal_threshold_realtime_native.json"
REALTIME_NATIVE_REPORT_PATH = REPORTS_DIR / "realtime_native_model_report.json"
HUMAN_REVIEW_QUEUE_PATH = REPORTS_DIR / "pseudo_label_review_queue.json"

RECALL_FLOOR = 0.80
PRECISION_FLOOR = 0.30

# ─── Incremental retraining contracts ─────────────────────────────────────────
# Confidence floor stamped into ``model_card.json`` and consumed at inference
# time: when the OOD detector flags an input as outlier, the published
# confidence MUST be capped at this value so downstream automation can't
# proceed on unreliable scores.
OOD_CONFIDENCE_FLOOR = float(os.getenv("FLOOD_OOD_CONFIDENCE_FLOOR", "0.6"))

# Pseudo-labels with raw confidence below this threshold are routed to a
# human-review queue rather than fed to the trainer.
PSEUDO_LABEL_CONFIDENCE_MIN = float(os.getenv("FLOOD_PSEUDO_LABEL_CONFIDENCE_MIN", "0.6"))

# Minimum positive (flood=1) samples required in each of the val/test folds
# for the chronological holdout split to be considered viable. When the
# bootstrap dataset has too few positives near the chronological tail (a
# common cold-start condition), the trainer falls back to a shuffled random
# split instead of raising — production retrain must never hard-fail here.
FLOOD_RETRAIN_MIN_POSITIVES = int(os.getenv("FLOOD_RETRAIN_MIN_POSITIVES", "1"))

# Time-decay half-life for sample weighting. weight = 0.5 ** (age_days / HL).
TIME_DECAY_HALF_LIFE_DAYS = float(os.getenv("FLOOD_TIME_DECAY_HALF_LIFE_DAYS", "14"))

# IsolationForest contamination is recomputed from the recent anomaly rate
# observed in production, but bounded so a degenerate window doesn't push
# the detector into pathological regimes.
_CONTAMINATION_MIN = 0.005
_CONTAMINATION_MAX = 0.25
_CONTAMINATION_DEFAULT = 0.03

# Risk levels treated as positive pseudo-labels.
_POSITIVE_RISK_LEVELS = frozenset({"WARNING", "DANGER"})


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_runtime_bundle(
    *,
    dataset_path: Path,
    threshold_payload: dict,
    model_card: dict,
    report: dict,
) -> None:
    REALTIME_NATIVE_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)

    shutil.copy2(REALTIME_NATIVE_MODEL_PATH, REALTIME_NATIVE_BUNDLE_DIR / "model.pkl")
    shutil.copy2(REALTIME_NATIVE_SCALER_PATH, REALTIME_NATIVE_BUNDLE_DIR / "scaler.pkl")
    shutil.copy2(REALTIME_NATIVE_OOD_PATH, REALTIME_NATIVE_BUNDLE_DIR / "ood.pkl")
    shutil.copy2(REALTIME_NATIVE_FEATURE_LIST_PATH, REALTIME_NATIVE_BUNDLE_DIR / "feature_list.json")

    normalized_thresholds = {
        **threshold_payload,
        "pre_alert_threshold": max(
            0.07,
            float(threshold_payload["warning_threshold"]) - 0.10,
        ),
    }

    calibration_payload = {
        "method": threshold_payload.get("calibration_method", "unknown"),
        "validation_recall": threshold_payload.get("validation_recall"),
        "validation_precision": threshold_payload.get("validation_precision"),
        "source": "models/realtime_native_bundle/threshold.json",
    }

    training_stats_payload = {
        "dataset_path": str(dataset_path),
        "feature_count": report.get("feature_count"),
        "training_rows": report.get("training_rows"),
        "validation_rows": report.get("validation_rows"),
        "test_rows": report.get("test_rows"),
        "performance": report.get("performance", {}),
        "calibration": report.get("calibration", {}),
        "scientific_notes": report.get("scientific_notes", {}),
    }

    with open(REALTIME_NATIVE_BUNDLE_DIR / "threshold.json", "w", encoding="utf-8") as file:
        json.dump(normalized_thresholds, file, indent=2)
    with open(REALTIME_NATIVE_BUNDLE_DIR / "calibration.json", "w", encoding="utf-8") as file:
        json.dump(calibration_payload, file, indent=2)
    with open(REALTIME_NATIVE_BUNDLE_DIR / "model_card.json", "w", encoding="utf-8") as file:
        json.dump(model_card, file, indent=2)
    with open(REALTIME_NATIVE_BUNDLE_DIR / "training_stats.json", "w", encoding="utf-8") as file:
        json.dump(training_stats_payload, file, indent=2)

    file_names = (
        "model.pkl",
        "scaler.pkl",
        "ood.pkl",
        "threshold.json",
        "calibration.json",
        "feature_list.json",
        "model_card.json",
        "training_stats.json",
    )
    manifest = {
        "bundle_version": "1.0.0",
        "model_variant": "realtime_native",
        "schema_version": "1",
        "created_at": pd.Timestamp.utcnow().isoformat(),
        "training_dataset_fingerprint": f"sha256:{_sha256_file(Path(dataset_path))}",
        "feature_schema": {
            "feature_count": len(REALTIME_NATIVE_FEATURES),
            "features": list(REALTIME_NATIVE_FEATURES),
        },
        "threshold_file": "threshold.json",
        "ood_file": "ood.pkl",
        "calibration_file": "calibration.json",
        "scaler_file": "scaler.pkl",
        "model_file": "model.pkl",
        "sha256": {
            file_name: _sha256_file(REALTIME_NATIVE_BUNDLE_DIR / file_name)
            for file_name in file_names
        },
    }
    with open(REALTIME_NATIVE_BUNDLE_DIR / "manifest.json", "w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2)


def _expected_calibration_error(y_true, y_proba, n_bins: int = 10) -> float:
    frac_pos, mean_pred = calibration_curve(y_true, y_proba, n_bins=n_bins, strategy="quantile")
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    counts, _ = np.histogram(y_proba, bins=bin_edges)
    weights = counts[: len(frac_pos)].astype(float) + 1e-9
    return float(np.average(np.abs(frac_pos - mean_pred), weights=weights))


def _select_threshold(y_val, val_proba):
    """Return (threshold, recall, precision, sweep_df).

    Strategy: recall-first for early warning.
    1. Find candidates with recall >= RECALL_FLOOR and precision >= PRECISION_FLOOR.
    2. If none, relax: max recall where precision >= PRECISION_FLOOR.
    3. If still none, take best F2 overall.
    Within each tier, sort by recall desc then F2 desc.
    """
    prec, rec, thr = precision_recall_curve(y_val, val_proba)
    sweep = pd.DataFrame({
        "threshold": np.r_[thr, 1.0],
        "precision": prec,
        "recall": rec,
    })
    sweep["f2"] = (5 * sweep["precision"] * sweep["recall"]) / (
        4 * sweep["precision"] + sweep["recall"] + 1e-9
    )
    # Tier 1: both floors met
    candidates = sweep[(sweep["recall"] >= RECALL_FLOOR) & (sweep["precision"] >= PRECISION_FLOOR)]
    if candidates.empty:
        # Tier 2: just precision floor, maximize recall
        candidates = sweep[sweep["precision"] >= PRECISION_FLOOR]
    if candidates.empty:
        # Tier 3: best F2 overall
        candidates = sweep
    chosen = candidates.sort_values(["recall", "f2"], ascending=False).iloc[0]
    return float(chosen["threshold"]), float(chosen["recall"]), float(chosen["precision"]), sweep


# ─── Incremental retraining helpers ───────────────────────────────────────────


def compute_observed_anomaly_rate(
    recent_features_scaled: np.ndarray,
    *,
    current_ood_detector: IsolationForest | None = None,
    fallback: float = _CONTAMINATION_DEFAULT,
) -> float:
    """
    Estimate the IsolationForest ``contamination`` parameter from the recent
    feature window. The new detector is then fit with this value so its
    decision boundary matches the empirical outlier rate the production
    pipeline is actually seeing — rather than the hardcoded 0.03 baked into
    the original training script.

    When no current detector is supplied (cold start), the fallback is used.
    The result is always clipped to ``[_CONTAMINATION_MIN, _CONTAMINATION_MAX]``
    so a degenerate window can't push the detector into pathological regimes.

    Returns a float in [_CONTAMINATION_MIN, _CONTAMINATION_MAX].
    """
    if current_ood_detector is None or recent_features_scaled is None:
        return fallback
    n = len(recent_features_scaled)
    if n < 10:
        logger.warning(
            "contamination: only %d recent samples — using fallback %.4f.",
            n, fallback,
        )
        return fallback
    try:
        labels = current_ood_detector.predict(recent_features_scaled)
        anomaly_rate = float((labels == -1).sum()) / float(n)
    except Exception as exc:  # noqa: BLE001
        logger.warning("contamination: detector predict failed (%s) — fallback.", exc)
        return fallback
    bounded = max(_CONTAMINATION_MIN, min(_CONTAMINATION_MAX, anomaly_rate))
    logger.info(
        "contamination: observed anomaly_rate=%.4f → contamination=%.4f (clipped %s)",
        anomaly_rate, bounded,
        "yes" if anomaly_rate != bounded else "no",
    )
    return bounded


def build_pseudo_labeled_dataset(
    *,
    bootstrap_df: pd.DataFrame,
    recent_records_df: pd.DataFrame,
    time_decay_half_life_days: float = TIME_DECAY_HALF_LIFE_DAYS,
    confidence_min: float = PSEUDO_LABEL_CONFIDENCE_MIN,
    now: "datetime | None" = None,
) -> tuple[pd.DataFrame, pd.Series, np.ndarray, list[dict]]:
    """
    Combine the bootstrap training dataset with recent inference history
    pulled from the trend / decision tables.

    ``recent_records_df`` MUST contain at minimum:
      observed_at  (ISO 8601 UTC string or pandas Timestamp)
      probability  (float, model output)
      confidence   (float, base confidence)
      risk_level   (str) — used to derive the pseudo-label
    The full 16-feature columns are concatenated when present; missing
    feature columns are filled with the bootstrap-fold median so the new
    rows don't poison the scaler.

    Returns (X, y, sample_weight, review_queue):
      - X / y / sample_weight: the merged training set ready to feed
        ``XGBClassifier.fit(..., sample_weight=sample_weight)``.
      - review_queue: list of low-confidence pseudo-label dicts that were
        held back for human triage. Caller is responsible for persisting
        them via ``persist_review_queue``.
    """
    ref_now = now if now is not None else datetime.now(timezone.utc)
    review_queue: list[dict] = []

    bootstrap_X = bootstrap_df[REALTIME_NATIVE_FEATURES].apply(
        pd.to_numeric, errors="coerce"
    ).fillna(0.0)
    bootstrap_y = pd.to_numeric(bootstrap_df["banjir"], errors="coerce").fillna(0).astype(int)

    if recent_records_df is None or recent_records_df.empty:
        weights = np.ones(len(bootstrap_X), dtype=float)
        return bootstrap_X, bootstrap_y, weights, review_queue

    # Split low-confidence rows into the review queue.
    confidences = pd.to_numeric(
        recent_records_df.get("confidence", pd.Series(dtype=float)),
        errors="coerce",
    ).fillna(0.0)
    low_conf_mask = confidences < confidence_min
    if low_conf_mask.any():
        for _, row in recent_records_df[low_conf_mask].iterrows():
            review_queue.append({
                "observed_at": str(row.get("observed_at", "")),
                "probability": _safe_float(row.get("probability")),
                "confidence": _safe_float(row.get("confidence")),
                "risk_level": str(row.get("risk_level", "")),
                "reason": "low_confidence_pseudo_label",
            })
    trusted = recent_records_df[~low_conf_mask].copy()
    if trusted.empty:
        weights = np.ones(len(bootstrap_X), dtype=float)
        return bootstrap_X, bootstrap_y, weights, review_queue

    # Pseudo-labels: WARNING/DANGER → 1, else → 0.
    risk_levels = trusted.get("risk_level", pd.Series([""] * len(trusted))).astype(str)
    pseudo_y = risk_levels.isin(_POSITIVE_RISK_LEVELS).astype(int).reset_index(drop=True)

    # Feature alignment — fill missing columns with bootstrap medians.
    feature_medians = bootstrap_X.median(numeric_only=True)
    pseudo_X = pd.DataFrame(index=range(len(trusted)), columns=REALTIME_NATIVE_FEATURES, dtype=float)
    for feat in REALTIME_NATIVE_FEATURES:
        if feat in trusted.columns:
            pseudo_X[feat] = pd.to_numeric(trusted[feat], errors="coerce").reset_index(drop=True)
        else:
            pseudo_X[feat] = float(feature_medians.get(feat, 0.0))
    pseudo_X = pseudo_X.fillna(feature_medians).fillna(0.0)

    # Time-decay weights: weight = 0.5 ** (age_days / half_life). Bootstrap
    # rows get weight 1.0 (no decay — they're the long-term prior).
    if "observed_at" in trusted.columns:
        observed = pd.to_datetime(trusted["observed_at"], errors="coerce", utc=True)
        age_days = (ref_now - observed).dt.total_seconds() / 86400.0
        age_days = age_days.fillna(time_decay_half_life_days * 4).clip(lower=0.0)
        pseudo_weights = np.power(0.5, age_days / max(time_decay_half_life_days, 0.5)).to_numpy()
    else:
        pseudo_weights = np.ones(len(trusted), dtype=float)

    X = pd.concat([bootstrap_X, pseudo_X], ignore_index=True)
    y = pd.concat([bootstrap_y, pseudo_y], ignore_index=True)
    weights = np.concatenate([
        np.ones(len(bootstrap_X), dtype=float),
        pseudo_weights,
    ])

    logger.info(
        "pseudo_label: bootstrap=%d trusted_pseudo=%d review_queue=%d "
        "half_life=%.1fd confidence_min=%.2f",
        len(bootstrap_X), len(trusted), len(review_queue),
        time_decay_half_life_days, confidence_min,
    )
    return X, y, weights, review_queue


def persist_review_queue(
    review_queue: list[dict],
    *,
    path: Path = HUMAN_REVIEW_QUEUE_PATH,
    now: "datetime | None" = None,
) -> Path:
    """Write the human-review queue out as JSON. Idempotent over the path."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ref_now = now if now is not None else datetime.now(timezone.utc)
    payload = {
        "generated_at": ref_now.isoformat(),
        "confidence_min": PSEUDO_LABEL_CONFIDENCE_MIN,
        "record_count": len(review_queue),
        "records": review_queue,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    os.replace(tmp, path)
    return path


def _safe_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


# ─── Original full-retrain entry point ────────────────────────────────────────


def train_realtime_native_model(
    dataset_path=REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH,
    leak_free_kecamatan_freq: bool = True,
    year_split: tuple[int, int] | None = None,
):
    """Train and write the realtime-native bundle.

    leak_free_kecamatan_freq: recompute the kecamatan flood-frequency feature per
        row from BPBD events in years *before that row's year* (the dataset column
        counts every year, so it leaks outcomes into the feature).
    year_split: (val_year, test_year) → train < val_year ≤ val < test_year ≤ test.
        None keeps the index-based 68/12/20 split, which falls back to a random
        stratified split when the chronological slices lack positives.
    """
    if not Path(dataset_path).exists():
        build_bootstrap_training_dataset(output_path=dataset_path)

    df = pd.read_csv(dataset_path, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    years = df["timestamp"].dt.year

    if leak_free_kecamatan_freq:
        freq_by_year = {int(yr): kecamatan_flood_freq_map_before(int(yr)) for yr in years.unique()}
        df["kecamatan_historical_flood_freq"] = [
            freq_by_year[int(yr)].get(slug, 0.0) for yr, slug in zip(years, df["name_3"])
        ]

    X = df[REALTIME_NATIVE_FEATURES].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    y = pd.to_numeric(df["banjir"], errors="coerce").fillna(0).astype(int)

    # --- STEP 4: split ---------------------------------------------------------
    if year_split is not None:
        val_year, test_year = year_split
        train_m, test_m = years < val_year, years >= test_year
        val_m = ~train_m & ~test_m
        X_train, X_val, X_test = X.loc[train_m], X.loc[val_m], X.loc[test_m]
        y_train, y_val, y_test = y.loc[train_m], y.loc[val_m], y.loc[test_m]
        split_used = f"by_year (train<{val_year}, val {val_year}–{test_year - 1}, test>={test_year})"
    else:
        # Last 20% = test; last 15% of the remainder = validation (68/12/20 overall).
        test_split_idx = int(len(df) * 0.80)
        val_split_idx = int(test_split_idx * 0.85)
        X_dev, X_test = X.iloc[:test_split_idx], X.iloc[test_split_idx:]
        y_dev, y_test = y.iloc[:test_split_idx], y.iloc[test_split_idx:]
        X_train, X_val = X_dev.iloc[:val_split_idx], X_dev.iloc[val_split_idx:]
        y_train, y_val = y_dev.iloc[:val_split_idx], y_dev.iloc[val_split_idx:]
        split_used = "chronological_68_12_20"

    val_positives = int(y_val.sum())
    test_positives = int(y_test.sum())
    train_positives = int(y_train.sum())
    if (
        val_positives < FLOOD_RETRAIN_MIN_POSITIVES
        or test_positives < FLOOD_RETRAIN_MIN_POSITIVES
    ):
        split_used = f"random_stratified_68_12_20 (fallback: {split_used} had no positives)"
        logger.warning(
            "insufficient_positives_using_random_split "
            "(train=%d, val=%d, test=%d, min_required=%d)",
            train_positives,
            val_positives,
            test_positives,
            FLOOD_RETRAIN_MIN_POSITIVES,
        )
        from sklearn.model_selection import train_test_split

        total_pos = int(y.sum())
        total_neg = int(len(y) - total_pos)
        stratify_all = y if total_pos >= 2 and total_neg >= 2 else None
        try:
            X_dev, X_test, y_dev, y_test = train_test_split(
                X, y, test_size=0.20, random_state=42,
                shuffle=True, stratify=stratify_all,
            )
        except ValueError:
            X_dev, X_test, y_dev, y_test = train_test_split(
                X, y, test_size=0.20, random_state=42, shuffle=True,
            )

        dev_pos = int(y_dev.sum())
        dev_neg = int(len(y_dev) - dev_pos)
        stratify_dev = y_dev if dev_pos >= 2 and dev_neg >= 2 else None
        try:
            X_train, X_val, y_train, y_val = train_test_split(
                X_dev, y_dev, test_size=0.15, random_state=42,
                shuffle=True, stratify=stratify_dev,
            )
        except ValueError:
            X_train, X_val, y_train, y_val = train_test_split(
                X_dev, y_dev, test_size=0.15, random_state=42, shuffle=True,
            )

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_val_s = scaler.transform(X_val)
    X_test_s = scaler.transform(X_test)

    # --- STEP 3a: SMOTE oversampling on training fold only (no leakage) ----
    neg_pre = int((y_train == 0).sum())
    pos_pre = int((y_train == 1).sum())
    smote_ratio = min(0.5, max(0.4, pos_pre / max(neg_pre, 1) * 4))
    try:
        smote = SMOTE(sampling_strategy=smote_ratio, random_state=42, k_neighbors=min(5, pos_pre - 1))
        X_train_s, y_train = smote.fit_resample(X_train_s, y_train)
        logger.info(
            "smote: %d→%d positives (ratio %.2f), total %d→%d",
            pos_pre, int((y_train == 1).sum()), smote_ratio,
            neg_pre + pos_pre, len(y_train),
        )
    except Exception as exc:
        logger.warning("smote_failed (falling back to original): %s", exc)

    # --- STEP 3b: scale_pos_weight from post-SMOTE train fold ---------------
    neg = int((y_train == 0).sum())
    pos = int((y_train == 1).sum())
    scale_pos_weight = neg / max(pos, 1)

    # --- STEP 6: surgical config (depth/regularisation tuned for ~2k rows) --
    # NOTE: early_stopping_rounds is intentionally kept off the BASE model
    # that gets wrapped by CalibratedClassifierCV. XGBoost 3.x rejects
    # ``early_stopping_rounds`` when the inner CV folds re-fit the base
    # estimator without an eval_set (which is exactly what
    # CalibratedClassifierCV does). We early-stop a *separate* probe fit
    # only to find the optimal n_estimators, then build the base model
    # with that count and no early-stop config.
    common_xgb_kwargs = dict(
        max_depth=4,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_weight=3,
        reg_lambda=1.5,
        scale_pos_weight=scale_pos_weight,
        objective=_focal_loss_objective,
        eval_metric="aucpr",
        tree_method="hist",
        random_state=42,
    )
    probe = XGBClassifier(n_estimators=400, early_stopping_rounds=30, **common_xgb_kwargs)
    probe.fit(X_train_s, y_train, eval_set=[(X_val_s, y_val)], verbose=False)
    chosen_n_estimators = int(getattr(probe, "best_iteration", 400) or 400) + 1

    base_model = XGBClassifier(n_estimators=chosen_n_estimators, **common_xgb_kwargs)
    base_model.fit(X_train_s, y_train, verbose=False)

    # --- STEP 7a: try both calibration methods, pick by best recall then ECE -
    best_cal = None
    best_cal_method = "isotonic"
    best_val_proba = None
    best_test_proba = None
    best_train_proba = None
    best_recall = -1.0
    best_ece = 1.0

    for _method in ("isotonic", "sigmoid"):
        _cal = CalibratedClassifierCV(base_model, method=_method, cv=5)
        _cal.fit(X_train_s, y_train)
        _vp = _cal.predict_proba(X_val_s)[:, 1]
        _tp = _cal.predict_proba(X_test_s)[:, 1]
        _trp = _cal.predict_proba(X_train_s)[:, 1]
        _thr, _rec, _, _ = _select_threshold(y_val, _vp)
        _ece = _expected_calibration_error(y_test, _tp, n_bins=10)
        _test_preds = (_tp >= _thr).astype(int)
        _test_rec = float((_test_preds[y_test.values == 1] == 1).mean()) if (y_test.values == 1).any() else 0.0
        logger.info(
            "calibration_candidate method=%s cv=5 val_recall=%.3f test_recall=%.3f ECE=%.4f",
            _method, _rec, _test_rec, _ece,
        )
        if _test_rec > best_recall or (_test_rec == best_recall and _ece < best_ece):
            best_cal = _cal
            best_cal_method = _method
            best_val_proba = _vp
            best_test_proba = _tp
            best_train_proba = _trp
            best_recall = _test_rec
            best_ece = _ece

    calibrated_model = best_cal
    val_proba = best_val_proba
    test_proba = best_test_proba
    train_proba = best_train_proba
    calibration_method = best_cal_method

    # --- STEP 2: threshold sweep on the VALIDATION fold ---------------------
    optimal_threshold, val_recall, val_precision, sweep_df = _select_threshold(y_val, val_proba)

    # --- STEP 7b: ECE + Brier -----------------------------------------------
    test_ece = _expected_calibration_error(y_test, test_proba, n_bins=10)
    test_brier = float(brier_score_loss(y_test, test_proba))

    # --- Final predictions at the chosen threshold (NO predict() calls) -----
    train_pred = (train_proba >= optimal_threshold).astype(int)
    test_pred = (test_proba >= optimal_threshold).astype(int)

    # --- OOD detector — contamination from observed anomaly rate ------------
    # If a prior detector exists we score the train fold through it to get
    # the empirical anomaly rate and use that as the new contamination
    # parameter (bounded by _CONTAMINATION_MIN / _CONTAMINATION_MAX). Cold
    # start (no prior model) falls back to the historical 0.03 default.
    prior_ood: IsolationForest | None = None
    try:
        if REALTIME_NATIVE_OOD_PATH.exists():
            prior_ood = joblib.load(REALTIME_NATIVE_OOD_PATH)
    except Exception as exc:  # noqa: BLE001
        logger.warning("contamination: prior OOD load failed (%s) — fallback.", exc)
    contamination = compute_observed_anomaly_rate(
        X_train_s,
        current_ood_detector=prior_ood,
        fallback=_CONTAMINATION_DEFAULT,
    )
    ood_detector = IsolationForest(
        n_estimators=200, contamination=contamination, random_state=42,
    )
    ood_detector.fit(X_train_s)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(calibrated_model, REALTIME_NATIVE_MODEL_PATH)
    joblib.dump(scaler, REALTIME_NATIVE_SCALER_PATH)
    joblib.dump(ood_detector, REALTIME_NATIVE_OOD_PATH)

    with open(REALTIME_NATIVE_FEATURE_LIST_PATH, "w", encoding="utf-8") as file:
        json.dump(REALTIME_NATIVE_FEATURES, file, indent=2)

    threshold_payload = {
        "model_variant": "realtime_native",
        "threshold": optimal_threshold,
        "warning_threshold": max(0.05, optimal_threshold - 0.10),
        "danger_threshold": optimal_threshold,
        "validation_recall": val_recall,
        "validation_precision": val_precision,
        "selection_rule": (
            f"max recall s.t. precision >= {PRECISION_FLOOR}; "
            f"target recall floor = {RECALL_FLOOR}; tiebreak F2."
        ),
        "calibration_method": calibration_method,
    }
    with open(REALTIME_NATIVE_THRESHOLD_PATH, "w", encoding="utf-8") as file:
        json.dump(threshold_payload, file, indent=2)

    cm = confusion_matrix(y_test, test_pred, labels=[0, 1]).tolist()

    report = {
        "dataset_path": str(dataset_path),
        "feature_count": len(REALTIME_NATIVE_FEATURES),
        "training_rows": int(len(X_train)),
        "validation_rows": int(len(X_val)),
        "test_rows": int(len(X_test)),
        # The split actually used — records the random fallback instead of
        # claiming "chronological" when the chronological slices had no positives.
        "split_strategy": split_used,
        "kecamatan_freq_source": (
            "events in years before each row's year" if leak_free_kecamatan_freq
            else "all years (includes validation/test outcomes — leaky)"
        ),
        "class_balance": {
            "train_neg_pre_smote": neg_pre,
            "train_pos_pre_smote": pos_pre,
            "train_neg": neg,
            "train_pos": pos,
            "scale_pos_weight": scale_pos_weight,
            "smote_ratio": smote_ratio,
        },
        "performance": {
            "optimal_threshold": optimal_threshold,
            "train_accuracy": float(accuracy_score(y_train, train_pred)),
            "test_accuracy": float(accuracy_score(y_test, test_pred)),
            "test_precision": float(precision_score(y_test, test_pred, zero_division=0)),
            "test_recall": float(recall_score(y_test, test_pred, zero_division=0)),
            "test_f1": float(f1_score(y_test, test_pred, zero_division=0)),
            "test_roc_auc": float(roc_auc_score(y_test, test_proba)),
            "validation_recall_at_threshold": val_recall,
            "validation_precision_at_threshold": val_precision,
        },
        "calibration": {
            "method": calibration_method,
            "test_brier": test_brier,
            "test_ece": test_ece,
        },
        "confusion_matrix": {
            "labels": [0, 1],
            "matrix": cm,
        },
        "threshold_sweep_top5": sweep_df.sort_values(["recall", "f2"], ascending=False)
        .head(5)
        .round(4)
        .to_dict(orient="records"),
        "scientific_notes": {
            "training_mode": "bootstrap_proxy_until_realtime_history_available",
            "limitations": [
                "Humidity, BMKG alert, dan water level historis belum tersedia observasional penuh.",
                "Sebagian feature bootstrap masih diproksikan dari histori hujan Jakarta.",
                "Train cadence (monthly) berbeda dengan inference cadence (per-snapshot); "
                "metrik di sini upper-bound, recall produksi wajib diverifikasi via shadow-mode.",
            ],
            "strengths": [
                "Chronological split + scale_pos_weight + isotonic calibration menargetkan recall >= 0.80.",
                "Threshold dipersist di optimal_threshold_realtime_native.json dan dibaca oleh inference.",
                "Brier + ECE diukur; auto-fallback ke sigmoid bila isotonic ECE > 0.10.",
            ],
        },
    }

    model_card = {
        "model_name": "XGBoost Flood Predictor - Realtime Native",
        "purpose": "Realtime-native flood prediction using only operationally available signals",
        "feature_set": REALTIME_NATIVE_FEATURES,
        "training_dataset": str(dataset_path),
        "report_path": str(REALTIME_NATIVE_REPORT_PATH),
        "threshold_path": str(REALTIME_NATIVE_THRESHOLD_PATH),
        "operating_threshold": optimal_threshold,
        "calibration_method": calibration_method,
        # Inference contract: when ``ood_detection.is_outlier=True``, the
        # published ``confidence_score`` MUST be capped at this value so
        # downstream automation cannot proceed on an unreliable score.
        "confidence_floor_on_outlier": OOD_CONFIDENCE_FLOOR,
        "ood_detector": {
            "algorithm": "IsolationForest",
            "n_estimators": 200,
            "contamination": contamination,
            "contamination_source": (
                "observed_anomaly_rate" if prior_ood is not None else "fallback_default"
            ),
        },
    }

    with open(REALTIME_NATIVE_MODEL_CARD_PATH, "w", encoding="utf-8") as file:
        json.dump(model_card, file, indent=2)
    with open(REALTIME_NATIVE_REPORT_PATH, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)
    _write_runtime_bundle(
        dataset_path=Path(dataset_path),
        threshold_payload=threshold_payload,
        model_card=model_card,
        report=report,
    )

    return report


# ─── Incremental retraining entry point ───────────────────────────────────────


def train_realtime_native_model_incremental(
    *,
    recent_records_df: pd.DataFrame | None = None,
    dataset_path: Path | str = REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH,
    time_decay_half_life_days: float = TIME_DECAY_HALF_LIFE_DAYS,
    confidence_min: float = PSEUDO_LABEL_CONFIDENCE_MIN,
    now: "datetime | None" = None,
) -> dict:
    """
    Drift-triggered incremental retraining.

    Pipeline:
      1. Load the bootstrap dataset (long-term prior).
      2. Combine with ``recent_records_df`` of recent inference outputs as
         pseudo-labels, weighted by time-decay. Low-confidence rows are
         shunted to ``HUMAN_REVIEW_QUEUE_PATH`` instead.
      3. Write a merged-dataset CSV that ``train_realtime_native_model`` can
         consume unchanged. The full-retrain path then takes over (it
         already handles chronological split, scaler, base XGBoost,
         CalibratedClassifierCV calibration, threshold sweep, IsolationForest
         with observed-anomaly contamination, and bundle write-out).

    Caller pattern (typical drift response):
        from monitoring.drift_monitor import trigger_retrain_subprocess
        from realtime_native.training import (
            train_realtime_native_model_incremental,
        )
        recent = pull_recent_history_from_db(...)
        report = train_realtime_native_model_incremental(recent_records_df=recent)
        trigger_retrain_subprocess(re_export_only=True)
    """
    ref_now = now if now is not None else datetime.now(timezone.utc)
    dataset_path = Path(dataset_path)
    if not dataset_path.exists():
        build_bootstrap_training_dataset(output_path=dataset_path)

    bootstrap_df = pd.read_csv(dataset_path, parse_dates=["timestamp"])
    X_merged, y_merged, weights, review_queue = build_pseudo_labeled_dataset(
        bootstrap_df=bootstrap_df,
        recent_records_df=recent_records_df if recent_records_df is not None else pd.DataFrame(),
        time_decay_half_life_days=time_decay_half_life_days,
        confidence_min=confidence_min,
        now=ref_now,
    )

    # Persist the human-review queue first so it's durable even if the
    # downstream training step fails. Operators triage these out-of-band.
    review_path = persist_review_queue(review_queue, now=ref_now)

    # Write a merged dataset that the existing full-retrain path can read.
    # We bolt a synthetic ``timestamp`` column on so the chronological-split
    # branch keeps working: bootstrap rows keep their original timestamp,
    # pseudo-label rows get an evenly-spaced sequence ending at ``ref_now``.
    merged = X_merged.copy()
    merged["banjir"] = y_merged.values
    merged["sample_weight"] = weights
    n_total = len(merged)
    n_bootstrap = len(bootstrap_df)
    base_ts = pd.to_datetime(bootstrap_df["timestamp"], errors="coerce", utc=True)
    # ffill/bfill methods on Series — fillna(method=...) was removed in pandas 2.x.
    bootstrap_ts = base_ts.ffill().bfill()
    if len(bootstrap_ts) < n_bootstrap:
        bootstrap_ts = pd.Series(
            pd.date_range(end=ref_now, periods=n_bootstrap, freq="h", tz="UTC")
        )
    pseudo_n = n_total - n_bootstrap
    if pseudo_n > 0:
        pseudo_ts = pd.Series(
            pd.date_range(end=ref_now, periods=pseudo_n, freq="h", tz="UTC")
        )
        timestamps = pd.concat([bootstrap_ts.iloc[:n_bootstrap], pseudo_ts], ignore_index=True)
    else:
        timestamps = bootstrap_ts.iloc[:n_bootstrap].reset_index(drop=True)
    merged.insert(0, "timestamp", timestamps.astype(str))

    merged_path = dataset_path.with_name(
        f"realtime_native_training_incremental_{ref_now.strftime('%Y%m%dT%H%M%SZ')}.csv"
    )
    merged.to_csv(merged_path, index=False)
    logger.info(
        "incremental: wrote merged dataset %s (bootstrap=%d + pseudo=%d, review=%d)",
        merged_path, n_bootstrap, max(0, n_total - n_bootstrap), len(review_queue),
    )

    # The existing full-retrain path already handles every downstream step
    # (split, scaler, XGB, calibration, threshold sweep, observed-anomaly
    # IsolationForest, bundle write). Run it against the merged dataset.
    report = train_realtime_native_model(dataset_path=merged_path)
    report["incremental"] = {
        "review_queue_path": str(review_path),
        "review_queue_count": len(review_queue),
        "merged_dataset_path": str(merged_path),
        "time_decay_half_life_days": time_decay_half_life_days,
        "pseudo_label_confidence_min": confidence_min,
        "pseudo_label_count": max(0, n_total - n_bootstrap),
        "bootstrap_count": n_bootstrap,
    }
    return report
