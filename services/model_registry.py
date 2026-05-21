import json
from dataclasses import dataclass
from functools import lru_cache
from typing import List

import joblib

from utils.paths import MODELS_DIR, REPORTS_DIR


@dataclass(frozen=True)
class ModelAssets:
    model: object
    scaler: object
    feature_names: List[str]
    threshold_config: dict
    model_card: dict
    project_summary: dict


def _load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


@lru_cache(maxsize=1)
def load_model_assets():
    return ModelAssets(
        model=joblib.load(MODELS_DIR / "flood_model_jakarta.pkl"),
        scaler=joblib.load(MODELS_DIR / "scaler_jakarta.pkl"),
        feature_names=_load_json(MODELS_DIR / "feature_list_jakarta.json"),
        threshold_config=_load_json(MODELS_DIR / "optimal_threshold.json"),
        model_card=_load_json(MODELS_DIR / "model_card_jakarta.json"),
        project_summary=_load_json(REPORTS_DIR / "project_summary.json"),
    )
