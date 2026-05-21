import hashlib
import json
from pathlib import Path

import joblib
import pytest

from realtime_native.bundle import (
    BundleCompatibilityError,
    load_runtime_bundle,
    runtime_version_report,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_bundle(
    tmp_path: Path,
    threshold_payload: dict,
    *,
    include_runtime_versions: bool = True,
    schema_version: str = "2",
) -> Path:
    bundle_dir = tmp_path / "realtime_native_bundle"
    bundle_dir.mkdir()

    joblib.dump({"asset": "model"}, bundle_dir / "model.pkl")
    joblib.dump({"asset": "scaler"}, bundle_dir / "scaler.pkl")
    joblib.dump({"asset": "ood"}, bundle_dir / "ood.pkl")

    (bundle_dir / "threshold.json").write_text(
        json.dumps(threshold_payload),
        encoding="utf-8",
    )
    (bundle_dir / "calibration.json").write_text(
        json.dumps({"method": "sigmoid"}),
        encoding="utf-8",
    )
    (bundle_dir / "feature_list.json").write_text(
        json.dumps(["rainfall_mm", "water_level_ratio"]),
        encoding="utf-8",
    )
    (bundle_dir / "model_card.json").write_text(
        json.dumps({"model_name": "bundle-test"}),
        encoding="utf-8",
    )
    (bundle_dir / "training_stats.json").write_text(
        json.dumps({"feature_count": 2}),
        encoding="utf-8",
    )

    hashes = {}
    for name in (
        "model.pkl",
        "scaler.pkl",
        "ood.pkl",
        "threshold.json",
        "calibration.json",
        "feature_list.json",
        "model_card.json",
        "training_stats.json",
    ):
        hashes[name] = _sha256(bundle_dir / name)

    manifest: dict = {
        "bundle_version": "test",
        "model_variant": "realtime_native",
        "schema_version": schema_version,
        "created_at": "2026-05-17T00:00:00Z",
        "training_dataset_fingerprint": "sha256:test",
        "feature_schema": {"feature_count": 2, "features": ["rainfall_mm", "water_level_ratio"]},
        "threshold_file": "threshold.json",
        "ood_file": "ood.pkl",
        "calibration_file": "calibration.json",
        "scaler_file": "scaler.pkl",
        "model_file": "model.pkl",
        "sha256": hashes,
    }
    if include_runtime_versions:
        # Mirror the runtime so the strict version guard passes — these
        # tests exercise threshold normalisation and hash validation, not
        # version-drift detection (which has its own explicit test below).
        manifest["runtime_versions"] = runtime_version_report()
    manifest_path = bundle_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_load_runtime_bundle_normalizes_threshold_triplet(tmp_path):
    manifest_path = _write_bundle(
        tmp_path,
        {
            "model_variant": "realtime_native",
            "danger_threshold": 0.45,
        },
    )

    bundle = load_runtime_bundle(manifest_path)

    # Threshold-normalisation rules (see bundle.derive_threshold_triplet):
    #   danger=0.45 (< 0.60) → derived_warning = 0.30, floor max(0.12, 0.30) = 0.30;
    #   pre_alert floor      = max(0.07, warning - 0.10)  = max(0.07, 0.20) = 0.20.
    assert bundle.thresholds["danger"] == 0.45
    assert bundle.thresholds["warning"] == 0.30
    assert bundle.thresholds["pre_alert"] == 0.20
    assert bundle.thresholds["source"] == "threshold.json"


def test_load_runtime_bundle_rejects_missing_runtime_versions(tmp_path):
    """Legacy schema_version=1 bundles without runtime_versions must fail loud."""
    manifest_path = _write_bundle(
        tmp_path,
        {"model_variant": "realtime_native", "danger_threshold": 0.45},
        include_runtime_versions=False,
        schema_version="1",
    )
    with pytest.raises(BundleCompatibilityError, match="runtime_versions"):
        load_runtime_bundle(manifest_path)


def test_load_runtime_bundle_rejects_hash_mismatch(tmp_path):
    manifest_path = _write_bundle(
        tmp_path,
        {
            "model_variant": "realtime_native",
            "pre_alert_threshold": 0.07,
            "warning_threshold": 0.12,
            "danger_threshold": 0.22,
        },
    )
    (manifest_path.parent / "threshold.json").write_text(
        json.dumps({"danger_threshold": 0.99}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="hash mismatch"):
        load_runtime_bundle(manifest_path)
