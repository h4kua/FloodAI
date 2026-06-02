"""
Generate calibration ground-truth labels for realtime predictions
using BPBD flood event data as proxy, then run ECE calibration.

Method:
  - For each prediction in realtime_pseudo_labels.csv, look up the
    corresponding month's flood activity from bpbd_flood_calendar.csv
    (or same month in previous year when current-year data is absent).
  - Estimate daily flood probability = event_count / (days_in_month * 2)
    (each BPBD event ≈ half a day of flooding in one kelurahan)
  - Remove physically impossible rows (rainfall_mm > 150).
  - Assign binary label using deterministic quantile split:
    top flood_fraction% predictions (by probability) get label=1.

Usage:
    python scripts/run_calibration_from_bpbd.py
"""
from __future__ import annotations

import csv
import sys
from calendar import monthrange
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PSEUDO_LABELS = ROOT / "data" / "processed" / "realtime_pseudo_labels.csv"
BPBD_CALENDAR = ROOT / "data" / "processed" / "bpbd_flood_calendar.csv"
OUT_LABELED   = ROOT / "data" / "processed" / "calibration_labeled.csv"

MAX_VALID_RAINFALL_MM = 150.0


def _load_bpbd_monthly() -> dict[tuple[int, int], int]:
    """Return {(year, month): event_count} from flood calendar."""
    cal: dict[tuple[int, int], int] = {}
    with open(BPBD_CALENDAR, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            year = int(row["year"])
            months = [int(m) for m in row["months_covered"].split(",")]
            events = int(row["event_count"])
            per_month = max(1, events // len(months))
            for m in months:
                key = (year, m)
                cal[key] = cal.get(key, 0) + per_month
    return cal


def _flood_fraction(year: int, month: int, cal: dict) -> float:
    """
    Estimate fraction of days in (year, month) that had flooding.
    Falls back to the same month in the previous year if unavailable.
    """
    days = monthrange(year, month)[1]
    for y in (year, year - 1):
        events = cal.get((y, month))
        if events is not None:
            return min(events / (days * 2.0), 1.0)
    return 0.0


def _load_predictions() -> list[dict]:
    with open(PSEUDO_LABELS, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    cal = _load_bpbd_monthly()
    print(f"BPBD monthly calendar: {len(cal)} entries")

    rows = _load_predictions()
    print(f"Realtime predictions: {len(rows)}")

    # Group predictions by (year, month)
    by_month: dict[tuple[int, int], list[dict]] = {}
    removed = 0
    for r in rows:
        try:
            rf = float(r.get("rainfall_mm", 0) or 0)
            if rf > MAX_VALID_RAINFALL_MM:
                removed += 1
                continue
            ts = r["timestamp"][:7]  # "YYYY-MM"
            yr, mo = int(ts[:4]), int(ts[5:7])
        except (ValueError, KeyError):
            removed += 1
            continue
        by_month.setdefault((yr, mo), []).append(r)

    print(f"Removed {removed} rows (rainfall > {MAX_VALID_RAINFALL_MM} mm — simulation/test data)")

    labeled: list[dict] = []
    print("\nMonth-level flood label summary:")
    print(f"  {'Year-Month':12s} {'Predictions':>12} {'FloodFrac':>10} {'Label=1':>8}")

    for (yr, mo), month_rows in sorted(by_month.items()):
        frac = _flood_fraction(yr, mo, cal)
        n = len(month_rows)
        n_flood = round(n * frac)

        # Deterministic: sort by probability descending, top n_flood get label=1
        sorted_rows = sorted(month_rows, key=lambda r: float(r["probability"]), reverse=True)
        for i, row in enumerate(sorted_rows):
            label = 1 if i < n_flood else 0
            labeled.append({
                "timestamp": row["timestamp"],
                "rainfall_mm": row["rainfall_mm"],
                "water_level_ratio": row["water_level_ratio"],
                "probability": row["probability"],
                "risk_level": row["risk_level"],
                "bpbd_year_source": yr if cal.get((yr, mo)) is not None else yr - 1,
                "bpbd_flood_fraction": round(frac, 4),
                "flood_label": label,
            })
        print(f"  {yr}-{mo:02d}       {n:>12} {frac:>10.3f} {n_flood:>8}")

    # Write labeled dataset
    with open(OUT_LABELED, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=labeled[0].keys())
        writer.writeheader()
        writer.writerows(labeled)
    print(f"\nLabeled dataset: {OUT_LABELED} ({len(labeled)} rows)")

    # Run calibration
    probs = [float(r["probability"]) for r in labeled]
    labels = [int(r["flood_label"]) for r in labeled]
    n_pos = sum(labels)
    print(f"\nClass balance: {n_pos} flood ({n_pos/len(labels)*100:.1f}%) / "
          f"{len(labels)-n_pos} no-flood ({(len(labels)-n_pos)/len(labels)*100:.1f}%)")

    try:
        from evaluation.calibration import compute_calibration_metrics
        result = compute_calibration_metrics(probs, labels)
        print("\nCalibration result:")
        print(f"  n          = {result['n']}")
        print(f"  ECE        = {result['ece']:.4f}  ({result['interpretations']['ece']})")
        print(f"  Brier      = {result['brier_score']:.4f}  ({result['interpretations']['brier_score']})")
        print(f"  Direction  = {result['overconfidence_direction']}")
        if result['interpretations'].get('small_n_warning'):
            print(f"  Warning    = {result['interpretations']['small_n_warning']}")
    except Exception as exc:
        print(f"\nCalibration error: {exc}")
        print("Tip: run from project root: python scripts/run_calibration_from_bpbd.py")


if __name__ == "__main__":
    main()
