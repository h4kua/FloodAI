#!/usr/bin/env python
"""
Retrain or re-export the realtime-native flood prediction bundle.

Two modes:

  default            Full retrain end-to-end against the current Python
                     runtime. Calls
                     ``app.realtime_native.training.train_realtime_native_model``
                     and then re-packages the produced artefacts into the
                     bundle directory with the new version-aware manifest.

  --re-export-only   Skip retraining. Take the existing bundle's
                     ``model.pkl`` (the calibrated sklearn ensemble), extract
                     the underlying XGBoost ``Booster`` and the per-fold
                     calibrators, then write:
                       * ``xgboost_model.json``  (native XGBoost binary; safe
                                                  across sklearn minor upgrades)
                       * ``calibration.json``    (extended schema with method
                                                  + per-fold calibrator params)
                       * ``manifest.json``       (with the new
                                                  ``runtime_versions`` block,
                                                  ``xgboost_model_file``
                                                  pointer, ``schema_version=2``,
                                                  refreshed sha256 hashes)
                     Use this when the calibrators were trained on a runtime
                     that is no longer reachable but the model logic is still
                     valid; the rebuild keeps the same predictions but moves
                     the wire format off pickle.

Both modes always emit a manifest that includes:
  * ``schema_version: "2"``
  * ``runtime_versions: {sklearn, xgboost, joblib, numpy, python}``
  * ``xgboost_model_file: "xgboost_model.json"``
  * sha256 of every asset listed in the manifest

Exit codes:
  0  success
  2  bundle directory not found and --re-export-only requested
  3  artefacts could not be parsed (corrupt model.pkl, etc.)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("retrain_bundle")

# Resolve project root relative to this file so the script is runnable from
# anywhere (``python scripts/retrain_bundle.py`` or invoked from CI).
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from utils.paths import REALTIME_NATIVE_BUNDLE_DIR  # noqa: E402


# ─── Asset names (relative to bundle dir) ────────────────────────────────────

_MODEL_FILE = "model.pkl"
_SCALER_FILE = "scaler.pkl"
_OOD_FILE = "ood.pkl"
_THRESHOLD_FILE = "threshold.json"
_CALIBRATION_FILE = "calibration.json"
_MANIFEST_FILE = "manifest.json"
_XGB_NATIVE_FILE = "xgboost_model.json"

_AUX_FILES = ("feature_list.json", "model_card.json", "training_stats.json")


# ─── Public entry point ──────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--re-export-only",
        action="store_true",
        help=(
            "Skip full retrain; extract the XGBoost Booster + calibrators "
            "from the existing model.pkl and rewrite manifest.json."
        ),
    )
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        default=REALTIME_NATIVE_BUNDLE_DIR,
        help="Destination bundle directory (default: models/realtime_native_bundle).",
    )
    args = parser.parse_args()

    bundle_dir: Path = args.bundle_dir
    if args.re_export_only:
        if not bundle_dir.exists():
            log.error("--re-export-only requires an existing bundle at %s", bundle_dir)
            return 2
        return _re_export_only(bundle_dir)

    return _full_retrain(bundle_dir)


# ─── Mode 1: full retrain ────────────────────────────────────────────────────


def _full_retrain(bundle_dir: Path) -> int:
    log.info("Full retrain against current runtime: %s", _runtime_versions())
    from realtime_native.training import train_realtime_native_model

    train_realtime_native_model()
    # train_realtime_native_model already writes the bundle directory; we
    # now upgrade it to the version-aware manifest.
    return _re_export_only(bundle_dir)


# ─── Mode 2: re-export only ──────────────────────────────────────────────────


def _re_export_only(bundle_dir: Path) -> int:
    log.info("Re-export bundle at %s", bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    model_path = bundle_dir / _MODEL_FILE

    if not model_path.exists():
        log.error("model.pkl is missing — cannot re-export. Run full retrain first.")
        return 2

    try:
        import joblib  # noqa: F401  (used below; eager import for clean error)
    except ImportError:
        log.exception("joblib is required to load model.pkl")
        return 3

    try:
        booster, calibrator_payload = _extract_xgb_native(model_path)
    except Exception:
        log.exception("Failed to extract XGBoost native model from %s", model_path)
        return 3

    native_path = bundle_dir / _XGB_NATIVE_FILE
    booster.save_model(str(native_path))
    log.info(
        "Wrote XGBoost native model → %s (%d bytes)",
        native_path,
        native_path.stat().st_size,
    )

    calibration_path = bundle_dir / _CALIBRATION_FILE
    _merge_calibration_payload(calibration_path, calibrator_payload)
    log.info("Updated calibration.json with per-fold parameters")

    _write_manifest(bundle_dir)
    log.info("Manifest written with runtime_versions and refreshed sha256 hashes")
    return 0


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _runtime_versions() -> dict[str, str]:
    versions: dict[str, str] = {"python": platform.python_version()}
    for module_name in ("sklearn", "xgboost", "joblib", "numpy"):
        try:
            module = __import__(module_name)
            versions[module_name] = getattr(module, "__version__", "<unknown>")
        except ImportError:
            versions[module_name] = "<not-installed>"
    return versions


def _extract_xgb_native(model_path: Path) -> tuple[object, dict]:
    """
    Load model.pkl and return (booster, calibration_payload).

    The pickled object can be:
      * CalibratedClassifierCV wrapping XGBClassifier → extract the
        underlying booster and every per-fold isotonic / sigmoid calibrator.
      * XGBClassifier directly → no calibration; empty payload.
      * Already a Booster → unchanged.

    Raises a clear RuntimeError if it is none of the above so the operator
    knows the bundle is unusable for native re-export and a full retrain is
    required.
    """
    import joblib
    import numpy as np

    obj = joblib.load(model_path)

    # Path 1: already a Booster
    try:
        import xgboost as xgb
        if isinstance(obj, xgb.Booster):
            return obj, {}
    except ImportError as exc:
        raise RuntimeError("xgboost not installed in the export environment") from exc

    # Path 2: XGBClassifier (no calibration wrapper)
    if hasattr(obj, "get_booster") and not hasattr(obj, "calibrated_classifiers_"):
        return obj.get_booster(), {}

    # Path 3: CalibratedClassifierCV (sklearn)
    if hasattr(obj, "calibrated_classifiers_"):
        return _extract_from_calibrated_ensemble(obj, np=np)

    raise RuntimeError(
        f"Unsupported model.pkl content: {type(obj).__name__}. "
        "Expected CalibratedClassifierCV, XGBClassifier, or Booster. "
        "Run a full retrain to regenerate a compatible bundle."
    )


def _extract_from_calibrated_ensemble(calibrated, *, np) -> tuple[object, dict]:
    """
    Walk a fitted ``CalibratedClassifierCV`` to:
      1. Recover the underlying XGBoost Booster from the first base estimator.
         (In our training flow base_model is fit BEFORE CalibratedClassifierCV
         wraps it, so every fold shares the same trained base.)
      2. Serialise each per-fold calibrator to JSON-safe parameters so the
         bundle can rebuild ``predict_proba`` without sklearn pickles.
    """
    method = (getattr(calibrated, "method", "") or "isotonic").lower()
    folds_payload: list[dict] = []

    base_booster = None
    for fold in calibrated.calibrated_classifiers_:
        base = getattr(fold, "estimator", None) or getattr(fold, "base_estimator", None)
        if base is not None and base_booster is None:
            if hasattr(base, "get_booster"):
                base_booster = base.get_booster()

        calibrators = getattr(fold, "calibrators_", None) or getattr(fold, "calibrators", None)
        if not calibrators:
            continue
        cal = calibrators[0]

        if method == "isotonic":
            xs = np.asarray(getattr(cal, "X_thresholds_", []), dtype=float).tolist()
            ys = np.asarray(getattr(cal, "y_thresholds_", []), dtype=float).tolist()
            folds_payload.append({"x": xs, "y": ys})
        else:  # sigmoid
            folds_payload.append({
                "a": float(getattr(cal, "a_", 0.0)),
                "b": float(getattr(cal, "b_", 0.0)),
            })

    if base_booster is None:
        raise RuntimeError(
            "Could not recover a base XGBoost booster from the calibrated "
            "ensemble. Run a full retrain."
        )

    return base_booster, {"method": method, "folds": folds_payload}


def _merge_calibration_payload(calibration_path: Path, extracted: dict) -> None:
    """
    Extend the existing calibration.json with the extracted method + folds.
    Preserves validation_recall / validation_precision / source so downstream
    consumers see a strict superset.
    """
    existing: dict = {}
    if calibration_path.exists():
        try:
            with open(calibration_path, "r", encoding="utf-8-sig") as fh:
                existing = json.load(fh)
        except Exception:
            log.warning("calibration.json unreadable; rewriting from scratch.")

    merged = {**existing, **extracted}
    _atomic_write_json(calibration_path, merged)


def _write_manifest(bundle_dir: Path) -> None:
    """
    Rebuild manifest.json with schema_version=2, runtime_versions, the
    xgboost_model_file pointer, and refreshed sha256 hashes for every asset.
    """
    manifest_path = bundle_dir / _MANIFEST_FILE
    feature_schema = _load_feature_schema(bundle_dir)

    asset_files: list[str] = [
        _MODEL_FILE,
        _SCALER_FILE,
        _OOD_FILE,
        _THRESHOLD_FILE,
        _CALIBRATION_FILE,
        *_AUX_FILES,
    ]
    native_path = bundle_dir / _XGB_NATIVE_FILE
    if native_path.exists():
        asset_files.append(_XGB_NATIVE_FILE)

    sha256_map: dict[str, str] = {}
    for name in asset_files:
        path = bundle_dir / name
        if not path.exists():
            log.warning("manifest sha256 skipped (missing asset): %s", name)
            continue
        sha256_map[name] = _sha256_file(path)

    training_dataset_fingerprint = _carry_training_dataset_fingerprint(manifest_path)

    manifest: dict[str, object] = {
        "bundle_version": "2.0.0",
        "model_variant": "realtime_native",
        "schema_version": "2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "training_dataset_fingerprint": training_dataset_fingerprint,
        "feature_schema": feature_schema,
        "threshold_file": _THRESHOLD_FILE,
        "ood_file": _OOD_FILE,
        "calibration_file": _CALIBRATION_FILE,
        "scaler_file": _SCALER_FILE,
        "model_file": _MODEL_FILE,
        "xgboost_model_file": _XGB_NATIVE_FILE if native_path.exists() else None,
        "runtime_versions": _runtime_versions(),
        "sha256": sha256_map,
    }
    if manifest["xgboost_model_file"] is None:
        manifest.pop("xgboost_model_file")

    _atomic_write_json(manifest_path, manifest)


def _carry_training_dataset_fingerprint(manifest_path: Path) -> str:
    """Preserve the previously-recorded dataset fingerprint when re-exporting."""
    if not manifest_path.exists():
        return "sha256:<unknown>"
    try:
        with open(manifest_path, "r", encoding="utf-8-sig") as fh:
            existing = json.load(fh)
    except Exception:
        return "sha256:<unknown>"
    return str(existing.get("training_dataset_fingerprint", "sha256:<unknown>"))


def _load_feature_schema(bundle_dir: Path) -> dict:
    feature_list_path = bundle_dir / "feature_list.json"
    if feature_list_path.exists():
        with open(feature_list_path, "r", encoding="utf-8-sig") as fh:
            features = json.load(fh)
    else:
        # Fall back to the canonical list from the feature builder.
        from realtime_native.feature_builder import REALTIME_NATIVE_FEATURES
        features = list(REALTIME_NATIVE_FEATURES)
    return {"feature_count": len(features), "features": list(features)}


def _atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=False)
        fh.flush()
    shutil.move(str(tmp), str(path))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    sys.exit(main())
