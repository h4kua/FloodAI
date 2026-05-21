import json
from pathlib import Path

from utils.paths import REPORTS_DIR


def _load_json_if_exists(path):
    if not Path(path).exists():
        return {}

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def refresh_project_summary(prediction):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = REPORTS_DIR / "project_summary.json"
    summary = _load_json_if_exists(summary_path)
    summary["real_time_prediction"] = {
        "risk_level": prediction["risk_level"],
        "probability": prediction["probability"],
        "confidence_score": prediction.get("confidence_score"),
        "data_quality_score": prediction.get("data_quality", {}).get("score"),
        "timestamp": prediction["timestamp"],
    }

    with open(summary_path, "w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)
