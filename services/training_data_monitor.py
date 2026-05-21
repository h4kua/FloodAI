from functools import lru_cache

import pandas as pd

from services.model_registry import load_model_assets
from utils.paths import PROCESSED_DATA_DIR


TRAINING_DATA_PATH = PROCESSED_DATA_DIR / "cleaned_flood_data_jakarta.csv"
OOD_EXCLUDED_FEATURES = {"year"}


@lru_cache(maxsize=1)
def load_training_feature_stats():
    assets = load_model_assets()
    df = pd.read_csv(TRAINING_DATA_PATH)
    feature_frame = df[assets.feature_names].apply(pd.to_numeric, errors="coerce")

    stats = {}
    for column in feature_frame.columns:
        series = feature_frame[column].dropna()
        stats[column] = {
            "mean": float(series.mean()),
            "std": float(series.std(ddof=0) or 0.0),
            "min": float(series.min()),
            "max": float(series.max()),
            "q01": float(series.quantile(0.01)),
            "q05": float(series.quantile(0.05)),
            "q95": float(series.quantile(0.95)),
            "q99": float(series.quantile(0.99)),
        }
    return stats


def detect_out_of_distribution(feature_values):
    stats = load_training_feature_stats()
    warnings = []
    in_distribution_count = 0

    for feature_name, value in feature_values.items():
        if feature_name in OOD_EXCLUDED_FEATURES:
            continue
        feature_stats = stats.get(feature_name)
        if feature_stats is None:
            continue

        numeric_value = float(value)
        q01 = feature_stats["q01"]
        q99 = feature_stats["q99"]
        q05 = feature_stats["q05"]
        q95 = feature_stats["q95"]
        std = feature_stats["std"]
        z_score = abs((numeric_value - feature_stats["mean"]) / std) if std else 0.0

        if q05 <= numeric_value <= q95:
            in_distribution_count += 1

        if numeric_value < q01 or numeric_value > q99 or z_score >= 3.0:
            warnings.append(
                {
                    "feature": feature_name,
                    "value": numeric_value,
                    "expected_range": [q01, q99],
                    "z_score": round(z_score, 3),
                    "severity": "high" if numeric_value < q01 or numeric_value > q99 else "medium",
                }
            )

    total_features = max(len(feature_values), 1)
    return {
        "warnings": warnings,
        "out_of_distribution_count": len(warnings),
        "in_distribution_ratio": in_distribution_count / total_features,
    }
