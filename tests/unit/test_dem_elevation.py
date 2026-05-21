from __future__ import annotations

import struct
from pathlib import Path

import pytest

import services.dem_elevation as dem_elevation


def _write_float32_strip_tiff(path: Path, rows: list[list[float]]) -> None:
    height = len(rows)
    width = len(rows[0])
    row_bytes = width * 4
    tag_count = 11
    ifd_offset = 8
    ifd_size = 2 + (tag_count * 12) + 4
    bytecounts_offset = ifd_offset + ifd_size
    strip_offsets_offset = bytecounts_offset + (height * 4)
    data_offset = strip_offsets_offset + (height * 4)
    strip_bytecounts = [row_bytes] * height
    strip_offsets = [data_offset + (idx * row_bytes) for idx in range(height)]

    entries = [
        (256, 4, 1, width),
        (257, 4, 1, height),
        (258, 3, 1, 32),
        (259, 3, 1, 1),
        (262, 3, 1, 1),
        (273, 4, height, strip_offsets_offset),
        (277, 3, 1, 1),
        (278, 4, 1, 1),
        (279, 4, height, bytecounts_offset),
        (284, 3, 1, 1),
        (339, 3, 1, 3),
    ]

    with path.open("wb") as fh:
        fh.write(b"II")
        fh.write(struct.pack("<H", 42))
        fh.write(struct.pack("<I", ifd_offset))
        fh.write(struct.pack("<H", len(entries)))
        for tag, field_type, count, value in entries:
            fh.write(struct.pack("<HHII", tag, field_type, count, value))
        fh.write(struct.pack("<I", 0))
        fh.write(struct.pack(f"<{height}I", *strip_bytecounts))
        fh.write(struct.pack(f"<{height}I", *strip_offsets))
        for row in rows:
            fh.write(struct.pack(f"<{width}f", *row))


def _reset_dem_cache() -> None:
    dem_elevation._dem_cache["initialized"] = False
    dem_elevation._dem_cache["tiles"] = {}
    dem_elevation._dem_cache["available_tiles"] = 0


def _row_col(origin: tuple[float, float], pixel_deg: float, lat: float, lon: float) -> tuple[int, int]:
    origin_lon, origin_lat = origin
    col = int((lon - origin_lon) / pixel_deg)
    row = int((origin_lat - lat) / pixel_deg)
    return row, col


@pytest.fixture
def synthetic_dem(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict:
    width = 200
    height = 200
    origin = (106.70, -6.10)
    pixel_deg = 0.001
    rows = [[12.0 for _ in range(width)] for _ in range(height)]

    pluit = (-6.12, 106.79)
    menteng = (-6.19, 106.83)
    pluit_row, pluit_col = _row_col(origin, pixel_deg, *pluit)
    menteng_row, menteng_col = _row_col(origin, pixel_deg, *menteng)

    rows[pluit_row][pluit_col] = -1.2
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            rows[pluit_row + dy][pluit_col + dx] = 0.8 + abs(dx) + abs(dy)

    rows[menteng_row][menteng_col] = 8.9
    rows[menteng_row][menteng_col + 1] = 4.1
    rows[menteng_row][menteng_col - 1] = 9.4
    rows[menteng_row - 1][menteng_col] = 9.8
    rows[menteng_row + 1][menteng_col] = 8.4
    rows[menteng_row + 1][menteng_col + 1] = 6.9

    tif_path = tmp_path / "synthetic_dem.tif"
    _write_float32_strip_tiff(tif_path, rows)

    registry = {
        "TEST_JAKARTA": {
            "path": str(tif_path),
            "bbox": {"lon_min": 106.70, "lon_max": 106.90, "lat_min": -6.30, "lat_max": -6.10},
            "origin": origin,
            "pixel_deg": pixel_deg,
            "width": width,
            "height": height,
            "strip_offset": None,
        }
    }

    monkeypatch.setattr(dem_elevation, "TILE_REGISTRY", registry)
    _reset_dem_cache()
    return {"pluit": pluit, "menteng": menteng}


def test_pluit_below_sea_level_classified_critical(synthetic_dem: dict) -> None:
    lat, lon = synthetic_dem["pluit"]

    result = dem_elevation.get_elevation(lat, lon)
    context = dem_elevation.get_elevation_context(lat, lon)

    assert result["elevation_m"] < 0
    assert dem_elevation.classify_flood_zone(result["elevation_m"]) == "critical"
    assert result["is_below_sea_level"] is True
    assert context["is_local_minimum"] is True
    assert context["depression_score"] > 0


def test_menteng_mid_elevation_range(synthetic_dem: dict) -> None:
    lat, lon = synthetic_dem["menteng"]

    result = dem_elevation.get_elevation(lat, lon)

    assert 5.0 <= result["elevation_m"] <= 15.0
    assert dem_elevation.classify_flood_zone(result["elevation_m"]) in {"medium", "low"}


def test_outside_coverage_returns_none(synthetic_dem: dict) -> None:
    result = dem_elevation.get_elevation(-7.25, 110.0)

    assert result["elevation_m"] is None


def test_missing_dem_does_not_crash(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.tif"
    monkeypatch.setattr(
        dem_elevation,
        "TILE_REGISTRY",
        {
            "MISSING": {
                "path": str(missing_path),
                "bbox": {"lon_min": 106.70, "lon_max": 106.90, "lat_min": -6.30, "lat_max": -6.10},
                "origin": (106.70, -6.10),
                "pixel_deg": 0.001,
                "width": 10,
                "height": 10,
                "strip_offset": None,
            }
        },
    )
    _reset_dem_cache()

    init_result = dem_elevation.initialize_dem()
    result = dem_elevation.get_elevation(-6.12, 106.79)

    assert init_result["available_tiles"] == 0
    assert result["elevation_m"] is None


def test_flow_direction_returns_valid_d8_direction(synthetic_dem: dict) -> None:
    lat, lon = synthetic_dem["menteng"]

    flow = dem_elevation.estimate_flow_direction(lat, lon)

    assert flow["flow_direction"] in {"N", "NE", "E", "SE", "S", "SW", "W", "NW", "flat"}
    assert flow["flow_direction"] != "unknown"
