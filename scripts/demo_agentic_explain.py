"""
CLI demo for the agentic Bahasa Indonesia flood explanation.

Runs three scenarios (Normal / Waspada / Bahaya) directly against the
FloodDecisionPipeline + Claude orchestrator — no HTTP. Prints only the
human-readable `penjelasan_ai` block. Raw prediction JSON is NEVER shown.

Usage:
    python -m scripts.demo_agentic_explain
    python -m scripts.demo_agentic_explain --no-claude   # force fallback
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from agents.llm_orchestrator import explain_flood_prediction  # noqa: E402
from pipeline.flood_pipeline import FloodDecisionPipeline  # noqa: E402


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scenario_normal() -> dict:
    return {
        "fetched_at_utc": _iso_now(),
        "location": "Jakarta Selatan",
        "openweather": {
            "main": {"temp": 28.0, "humidity": 70},
            "rain": {"1h": 2},
            "coord": {"lat": -6.2615, "lon": 106.8106},
        },
        "poskobanjir": [
            {"wilayah": "Jakarta Selatan", "tinggi_air": 50, "status": "Normal"}
        ],
        "bmkg_alerts": [],
    }


def _scenario_warning() -> dict:
    return {
        "fetched_at_utc": _iso_now(),
        "location": "Jakarta Utara",
        "openweather": {
            "main": {"temp": 27.0, "humidity": 88},
            "rain": {"1h": 25},
            "coord": {"lat": -6.1380, "lon": 106.8650},
        },
        "poskobanjir": [
            {"wilayah": "Jakarta Utara", "tinggi_air": 180, "status": "Siaga 3"}
        ],
        "bmkg_alerts": [
            {
                "headline": "Hujan Sangat Lebat dan Angin Kencang Jakarta",
                "severity": "Severe",
                "certainty": "Observed",
                "urgency": "Immediate",
            }
        ],
    }


def _scenario_danger() -> dict:
    return {
        "fetched_at_utc": _iso_now(),
        "location": "Jakarta Utara",
        "openweather": {
            "main": {"temp": 26.0, "humidity": 95},
            "rain": {"1h": 80},
            "coord": {"lat": -6.1380, "lon": 106.8650},
        },
        "poskobanjir": [
            {"wilayah": "Jakarta Utara", "tinggi_air": 900, "status": "Siaga 1"}
        ],
        "bmkg_alerts": [
            {
                "headline": "Peringatan Dini Banjir Bandang Jakarta",
                "severity": "Extreme",
                "certainty": "Observed",
                "urgency": "Immediate",
            }
        ],
    }


_STATUS_BADGE = {
    "AMAN": "🟢",
    "WASPADA": "🟡",
    "BAHAYA": "🔴",
}


def _print_banner(title: str) -> None:
    width = 42
    bar = "═" * width
    pad = max(0, width - 2 - len(title))
    line = f"║  {title}{' ' * pad}║"
    print()
    print(f"╔{bar}╗")
    print(line)
    print(f"╚{bar}╝")


def _print_explanation(explanation: dict) -> None:
    status = str(explanation.get("status_banjir") or "UNKNOWN").upper()
    badge = _STATUS_BADGE.get(status, "⚪")
    print(f"{badge} STATUS: {status}\n")

    print("📋 PENJELASAN:")
    for line in str(explanation.get("penjelasan") or "").splitlines() or [""]:
        print(f"   {line}".rstrip())
    print()

    print("⚡ TINDAKAN PRIORITAS:")
    tindakan = explanation.get("tindakan") or []
    if isinstance(tindakan, list):
        for idx, item in enumerate(tindakan, start=1):
            print(f"   {idx}. {item}")
    print()

    pop = explanation.get("populasi_terdampak")
    pop_text = pop if pop else "tidak tersedia"
    print(f"👥 Populasi terdampak: {pop_text}")
    print(f"📊 Kepercayaan sistem: {explanation.get('tingkat_kepercayaan') or 'n/a'}")
    print(f"📢 Pesan petugas: {explanation.get('pesan_petugas') or '-'}")


async def _run_scenario(
    pipeline: FloodDecisionPipeline,
    title: str,
    snapshot: dict,
    use_claude: bool,
) -> None:
    _print_banner(title)
    prediction = await asyncio.to_thread(pipeline.run, snapshot)
    if use_claude:
        explanation = await explain_flood_prediction(prediction)
    else:
        from agents.llm_orchestrator import _fallback_explanation
        explanation = _fallback_explanation(prediction)
    _print_explanation(explanation)


async def _main(use_claude: bool) -> int:
    pipeline = FloodDecisionPipeline(persist=False)
    scenarios = [
        ("SKENARIO 1: KONDISI NORMAL", _scenario_normal()),
        ("SKENARIO 2: KONDISI WASPADA", _scenario_warning()),
        ("SKENARIO 3: KONDISI BAHAYA", _scenario_danger()),
    ]
    for title, snapshot in scenarios:
        try:
            await _run_scenario(pipeline, title, snapshot, use_claude)
        except Exception as exc:  # noqa: BLE001 — demo must keep going
            print(f"\n[!] Skenario gagal: {type(exc).__name__}: {exc}")
    print()
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Demo CLI penjelasan agentic flood AI dalam Bahasa Indonesia."
    )
    parser.add_argument(
        "--no-claude",
        action="store_true",
        help="Lewati pemanggilan Claude dan gunakan template fallback deterministik.",
    )
    return parser


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "WARNING"))
    args = _build_arg_parser().parse_args()
    sys.exit(asyncio.run(_main(use_claude=not args.no_claude)))
