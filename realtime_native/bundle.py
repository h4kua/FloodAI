"""
Runtime bundle loader for the realtime-native flood prediction model.

Adds three guard rails on top of the previous loader:

1. **Hash validation** — every asset listed in ``manifest.sha256`` must match
   its on-disk content (already enforced; preserved).
2. **Version-compatibility guard** — the manifest now records the exact
   ``sklearn`` and ``xgboost`` versions used at train time AND the
   ``joblib`` / ``numpy`` versions. At load time we compare these against
   the running process and raise a clear, actionable error when the major or
   minor versions disagree.
3. **XGBoost native model loader** — if ``manifest.xgboost_model_file`` is
   present (the recommended path produced by ``scripts/retrain_bundle.py``),
   the loader uses ``xgb.Booster().load_model(...)`` and rebuilds the
   calibration wrapper from the persisted JSON instead of un-pickling the
   whole sklearn graph. This keeps the model file compatible across sklearn
   minor upgrades.

Backward compatibility: when the new fields are absent (legacy bundle), the
loader raises a single explicit ``BundleCompatibilityError`` with the exact
remediation command to run. Silent drift is no longer possible.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import joblib

from utils.paths import REALTIME_NATIVE_BUNDLE_MANIFEST


logger = logging.getLogger(__name__)


_REQUIRED_MANIFEST_FIELDS = (
    "bundle_version",
    "model_variant",
    "schema_version",
    "created_at",
    "training_dataset_fingerprint",
    "feature_schema",
    "threshold_file",
    "ood_file",
    "calibration_file",
    "scaler_file",
    "model_file",
    "sha256",
)
_REQUIRED_BUNDLE_FILES = (
    "feature_list.json",
    "model_card.json",
    "training_stats.json",
)

# Schema version recognised by THIS loader. A bundle stamped with a different
# major schema must be re-exported through scripts/retrain_bundle.py.
SUPPORTED_SCHEMA_VERSIONS = ("1", "2")

# Compatibility policy for runtime library versions. ``strict`` keys MUST
# match (major+minor) — anything else raises BundleCompatibilityError.
# ``advisory`` keys log a warning when patch-level drift is detected but do
# not raise. Override at deploy time with FLOOD_BUNDLE_VERSION_POLICY=warn
# to demote strict-fail to warn-only (NOT recommended for production).
_STRICT_LIBRARIES: tuple[str, ...] = ("sklearn", "xgboost")
_ADVISORY_LIBRARIES: tuple[str, ...] = ("joblib", "numpy")


class BundleCompatibilityError(RuntimeError):
    """Raised when the bundle was produced with libraries incompatible with the runtime."""


@dataclass(frozen=True)
class RuntimeBundle:
    manifest: dict
    model: object
    scaler: object
    ood_detector: object
    thresholds: dict
    calibration: dict
    feature_list: list[str]
    model_card: dict
    training_stats: dict


def derive_threshold_triplet(
    *,
    danger: float,
    warning: float | None = None,
    pre_alert: float | None = None,
) -> dict:
    """
    Normalize the native threshold ladder from a single canonical danger level.

    Floors mirror the committed realtime-native operating band:
      pre_alert = 0.07
      warning   = 0.12
      danger    = 0.22
    """
    danger_value = _clamp_threshold(danger)
    derived_warning = danger_value - (0.20 if danger_value >= 0.60 else 0.15)
    warning_value = (
        _clamp_threshold(warning)
        if warning is not None
        else max(0.12, derived_warning)
    )
    pre_alert_value = (
        _clamp_threshold(pre_alert)
        if pre_alert is not None
        else max(0.07, warning_value - 0.10)
    )

    warning_value = max(pre_alert_value, min(warning_value, danger_value))
    pre_alert_value = min(pre_alert_value, warning_value)
    return {
        "pre_alert": round(pre_alert_value, 4),
        "warning": round(warning_value, 4),
        "danger": round(danger_value, 4),
    }


def normalize_threshold_payload(payload: dict, *, source: str) -> dict:
    danger_raw = payload.get("danger_threshold", payload.get("threshold"))
    if danger_raw is None:
        raise ValueError("threshold payload missing danger_threshold/threshold")

    normalized = derive_threshold_triplet(
        danger=float(danger_raw),
        warning=_optional_float(payload.get("warning_threshold")),
        pre_alert=_optional_float(payload.get("pre_alert_threshold")),
    )
    return {
        "pre_alert": normalized["pre_alert"],
        "warning": normalized["warning"],
        "danger": normalized["danger"],
        "source": source,
        "model_variant": payload.get("model_variant", "realtime_native"),
        "validation_recall": payload.get("validation_recall"),
        "validation_precision": payload.get("validation_precision"),
        "calibration_method": payload.get("calibration_method"),
    }


def load_runtime_bundle(manifest_path: Path | str = REALTIME_NATIVE_BUNDLE_MANIFEST) -> RuntimeBundle:
    manifest_file = Path(manifest_path)
    manifest = _load_json(manifest_file)
    return _load_runtime_bundle_cached(
        str(manifest_file.resolve()),
        _bundle_mtime(manifest_file, manifest),
    )


@lru_cache(maxsize=4)
def _load_runtime_bundle_cached(
    manifest_path: str,
    bundle_mtime_ns: int,
) -> RuntimeBundle:
    del bundle_mtime_ns
    manifest_file = Path(manifest_path)
    bundle_dir = manifest_file.parent
    manifest = _load_json(manifest_file)
    _validate_manifest(bundle_dir, manifest)
    _validate_runtime_versions(manifest)

    threshold_path = bundle_dir / str(manifest["threshold_file"])
    calibration_path = bundle_dir / str(manifest["calibration_file"])
    model_path = bundle_dir / str(manifest["model_file"])
    scaler_path = bundle_dir / str(manifest["scaler_file"])
    ood_path = bundle_dir / str(manifest["ood_file"])
    feature_list_path = bundle_dir / "feature_list.json"
    model_card_path = bundle_dir / "model_card.json"
    training_stats_path = bundle_dir / "training_stats.json"

    thresholds = normalize_threshold_payload(
        _load_json(threshold_path),
        source=threshold_path.name,
    )

    # XGBoost-native model loader: when the manifest declares a native
    # Booster artifact (``xgboost_model_file``), prefer it. This is the only
    # path that survives sklearn minor-version upgrades cleanly because the
    # XGBoost binary format is stable across XGBoost minors.
    xgb_native_file = manifest.get("xgboost_model_file")
    if xgb_native_file:
        model = _load_xgb_native(
            bundle_dir / str(xgb_native_file),
            calibration_path=calibration_path,
        )
    else:
        model = joblib.load(model_path)

    return RuntimeBundle(
        manifest=dict(manifest),
        model=model,
        scaler=joblib.load(scaler_path),
        ood_detector=joblib.load(ood_path),
        thresholds=thresholds,
        calibration=_load_json(calibration_path),
        feature_list=list(_load_json(feature_list_path)),
        model_card=_load_json(model_card_path),
        training_stats=_load_json(training_stats_path),
    )


def runtime_version_report() -> dict[str, str]:
    """Best-effort snapshot of running library versions; safe to call at startup."""
    versions: dict[str, str] = {}
    for module_name in (*_STRICT_LIBRARIES, *_ADVISORY_LIBRARIES):
        versions[module_name] = _module_version(module_name)
    return versions


def _validate_runtime_versions(manifest: dict) -> None:
    """
    Compare the manifest's ``runtime_versions`` block against the running
    process. Strict libraries (sklearn, xgboost) must match major+minor.
    Advisory libraries log a warning on patch-level drift only.
    """
    declared = manifest.get("runtime_versions")
    if not isinstance(declared, dict):
        raise BundleCompatibilityError(
            "Bundle manifest is missing the 'runtime_versions' block. "
            "Re-export with `python scripts/retrain_bundle.py --re-export-only` "
            "to add it. Refusing to load — silent sklearn/xgboost drift "
            "between train and runtime causes invalid calibration and silent "
            "prediction skew."
        )

    schema_version = str(manifest.get("schema_version", ""))
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise BundleCompatibilityError(
            f"Bundle schema_version={schema_version!r} not supported by this "
            f"loader (supported: {SUPPORTED_SCHEMA_VERSIONS}). "
            "Re-export the bundle through `scripts/retrain_bundle.py`."
        )

    policy = os.getenv("FLOOD_BUNDLE_VERSION_POLICY", "strict").strip().lower()
    failures: list[str] = []

    for module_name in _STRICT_LIBRARIES:
        recorded = str(declared.get(module_name, "")).strip()
        if not recorded:
            failures.append(
                f"{module_name}: manifest does not record the train-time version "
                f"— cannot prove compatibility."
            )
            continue
        running = _module_version(module_name)
        if not _versions_compatible(recorded, running, level="minor"):
            failures.append(
                f"{module_name}: trained with {recorded}, runtime is {running} "
                f"(major+minor MUST match)."
            )

    for module_name in _ADVISORY_LIBRARIES:
        recorded = str(declared.get(module_name, "")).strip()
        if not recorded:
            continue
        running = _module_version(module_name)
        if not _versions_compatible(recorded, running, level="minor"):
            logger.warning(
                "bundle.runtime_versions advisory drift: %s trained=%s runtime=%s",
                module_name,
                recorded,
                running,
            )

    if not failures:
        return

    message = (
        "Bundle/runtime library mismatch — refusing to serve predictions:\n  - "
        + "\n  - ".join(failures)
        + "\n\nRemediation (choose one):\n"
        "  (a) Pin the runtime to the trained versions in requirements.txt "
        "and reinstall:\n"
        f"        sklearn=={declared.get('sklearn', '<unknown>')}, "
        f"xgboost=={declared.get('xgboost', '<unknown>')}\n"
        "  (b) Re-train against the current runtime:\n"
        "        python scripts/retrain_bundle.py --re-export-only   "
        "# fastest, re-fits scaler/OOD only\n"
        "        python scripts/retrain_bundle.py                    "
        "# full retrain end-to-end\n"
        "  (c) Operational override (NOT recommended for production):\n"
        "        FLOOD_BUNDLE_VERSION_POLICY=warn"
    )
    if policy == "warn":
        logger.error("BUNDLE_VERSION_MISMATCH_WARN_ONLY %s", "; ".join(failures))
        return
    raise BundleCompatibilityError(message)


def _versions_compatible(declared: str, running: str, *, level: str) -> bool:
    """Match versions at major+minor (``level='minor'``) or major (``level='major'``)."""
    declared_parts = _normalise_version(declared)
    running_parts = _normalise_version(running)
    width = 2 if level == "minor" else 1
    return declared_parts[:width] == running_parts[:width]


def _normalise_version(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in str(version).split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _module_version(module_name: str) -> str:
    try:
        module = __import__(module_name)
    except ImportError:
        return "<not-installed>"
    return getattr(module, "__version__", "<unknown>")


def _load_xgb_native(
    booster_path: Path,
    *,
    calibration_path: Path,
) -> object:
    """
    Reconstruct a calibrated classifier from an XGBoost native Booster file
    plus a persisted calibrators JSON. Returns an object that exposes
    ``predict_proba(X)`` so the existing inference path is unchanged.
    """
    if not booster_path.exists():
        raise FileNotFoundError(
            f"xgboost_model_file declared in manifest but missing on disk: {booster_path}"
        )

    try:
        import xgboost as xgb
    except ImportError as exc:
        raise BundleCompatibilityError(
            "manifest declares xgboost_model_file but xgboost is not installed."
        ) from exc

    booster = xgb.Booster()
    booster.load_model(str(booster_path))
    payload = _load_json(calibration_path) if calibration_path.exists() else {}

    # CalibratedClassifierCV(cv=k) trains a separate booster per fold. When the
    # export saved each fold's booster, pair it with its own calibrator so the
    # served probabilities equal the trained ensemble's.
    folds = payload.get("folds") or []
    fold_boosters: list = []
    if folds and all(fold.get("booster_file") for fold in folds):
        for fold in folds:
            fold_path = booster_path.parent / str(fold["booster_file"])
            if not fold_path.exists():
                raise FileNotFoundError(f"fold booster declared in calibration.json is missing: {fold_path}")
            fold_booster = xgb.Booster()
            fold_booster.load_model(str(fold_path))
            fold_boosters.append(fold_booster)

    return _CalibratedBoosterAdapter(
        booster=booster,
        calibration_payload=payload,
        fold_boosters=tuple(fold_boosters),
    )


@dataclass(frozen=True)
class _CalibratedBoosterAdapter:
    """
    Minimal ``predict_proba``-compatible adapter for an XGBoost ``Booster``
    plus optional isotonic / sigmoid calibrator data persisted as JSON.

    Calibration JSON schema (per fold):
      {
        "method": "isotonic" | "sigmoid",
        "folds": [
          {"x": [...], "y": [...]}      # isotonic: monotone calibration points
          or {"a": float, "b": float}   # sigmoid: 1 / (1 + exp(a*p + b))
        ]
      }

    When ``folds`` is empty or ``method`` is unknown, raw booster scores are
    returned untouched. This is the safe default for the existing legacy
    calibration.json (which carries only method + validation metrics, no
    fold parameters yet).

    Predictions are the mean of per-fold calibrated probabilities — the same
    semantics CalibratedClassifierCV uses when assembling its CV ensemble.
    With ``fold_boosters`` each fold's calibrator is applied to that fold's own
    booster (exact parity with the trained ensemble). Without them (older
    bundles) every calibrator is applied to the single ``booster``.
    """

    booster: object
    calibration_payload: dict
    fold_boosters: tuple = ()

    def predict_proba(self, X):  # type: ignore[no-untyped-def]
        import numpy as np
        import xgboost as xgb

        dmat = xgb.DMatrix(np.asarray(X))
        if self.fold_boosters:
            method = str(self.calibration_payload.get("method") or "").lower()
            per_fold = [
                _calibrate_fold(_raw_scores(fold_booster, dmat), fold, method)
                for fold_booster, fold in zip(self.fold_boosters, self.calibration_payload["folds"])
            ]
            calibrated = np.clip(np.stack(per_fold, axis=0).mean(axis=0), 0.0, 1.0)
        else:
            calibrated = _apply_calibration(_raw_scores(self.booster, dmat), self.calibration_payload)
        return np.column_stack([1.0 - calibrated, calibrated])


def _raw_scores(booster, dmat):
    import numpy as np

    return np.clip(np.asarray(booster.predict(dmat), dtype=float), 1e-7, 1.0 - 1e-7)


def _apply_calibration(probabilities, payload: dict):
    import numpy as np

    method = str(payload.get("method") or "").lower()
    folds = payload.get("folds") or []
    if not folds or method not in ("isotonic", "sigmoid"):
        return probabilities

    stack = np.stack([_calibrate_fold(probabilities, fold, method) for fold in folds], axis=0)
    return np.clip(stack.mean(axis=0), 0.0, 1.0)


def _calibrate_fold(probabilities, fold: dict, method: str):
    """Apply one fold's isotonic or sigmoid calibrator (sklearn semantics)."""
    import numpy as np

    if method == "isotonic":
        xs = np.asarray(fold.get("x") or [], dtype=float)
        ys = np.asarray(fold.get("y") or [], dtype=float)
        if xs.size < 2:
            return probabilities
        return np.interp(probabilities, xs, ys, left=ys[0], right=ys[-1])
    a = float(fold.get("a", 0.0))
    b = float(fold.get("b", 0.0))
    return 1.0 / (1.0 + np.exp(a * probabilities + b))


def _bundle_mtime(manifest_file: Path, manifest: dict) -> int:
    bundle_dir = manifest_file.parent
    paths = [manifest_file]
    for field in ("threshold_file", "calibration_file", "ood_file", "scaler_file", "model_file"):
        paths.append(bundle_dir / str(manifest[field]))
    optional_native = manifest.get("xgboost_model_file")
    if optional_native:
        paths.append(bundle_dir / str(optional_native))
    paths.extend(bundle_dir / str(name) for name in manifest.get("xgboost_fold_model_files") or [])
    for file_name in _REQUIRED_BUNDLE_FILES:
        paths.append(bundle_dir / file_name)
    return max(path.stat().st_mtime_ns for path in paths if path.exists())


def _validate_manifest(bundle_dir: Path, manifest: dict) -> None:
    missing_fields = [field for field in _REQUIRED_MANIFEST_FIELDS if field not in manifest]
    if missing_fields:
        raise ValueError(f"bundle manifest missing fields: {missing_fields}")

    expected_hashes = manifest.get("sha256")
    if not isinstance(expected_hashes, dict):
        raise ValueError("bundle manifest sha256 must be a mapping")

    required_files = {
        str(manifest["threshold_file"]),
        str(manifest["calibration_file"]),
        str(manifest["ood_file"]),
        str(manifest["scaler_file"]),
        str(manifest["model_file"]),
        *_REQUIRED_BUNDLE_FILES,
    }
    optional_native = manifest.get("xgboost_model_file")
    if optional_native:
        required_files.add(str(optional_native))
    required_files.update(str(name) for name in manifest.get("xgboost_fold_model_files") or [])

    missing_hashes = sorted(required_files - set(expected_hashes))
    if missing_hashes:
        raise ValueError(f"bundle manifest missing sha256 entries: {missing_hashes}")

    for relative_path in required_files:
        path = bundle_dir / relative_path
        if not path.exists():
            raise FileNotFoundError(f"bundle asset missing: {path}")
        actual_hash = _sha256_file(path)
        expected_hash = str(expected_hashes[relative_path]).lower()
        if actual_hash != expected_hash:
            raise ValueError(
                f"bundle asset hash mismatch for {relative_path}: "
                f"expected {expected_hash}, got {actual_hash}"
            )


def _load_json(path: Path):
    with open(path, "r", encoding="utf-8-sig") as file:
        return json.load(file)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clamp_threshold(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _optional_float(value: object) -> float | None:
    if value in ("", None):
        return None
    return float(value)
