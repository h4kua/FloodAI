"""
DEMNAS elevation access helpers.

Reads point elevations directly from local DEMNAS TIFF strips using only the
Python standard library. The implementation is intentionally conservative:

* Lazy, best-effort initialisation
* No startup crash when DEM files are missing or malformed
* Seek-based strip reads only; never loads full tiles into memory
* Thread-safe singleton metadata cache for FastAPI read workloads
"""

from __future__ import annotations

import logging
import math
import os
import struct
import threading
from pathlib import Path
from typing import BinaryIO

from utils.paths import PROJECT_ROOT


_log = logging.getLogger(__name__)

DEM_SOURCE_NAME = "DEMNAS_BIG_8m"
_DEFAULT_DEM_DIR = PROJECT_ROOT / "demnas"
_FLOAT32_BYTES = 4
_METERS_PER_DEGREE = 111_320.0
_FLOAT_TOLERANCE_M = 0.05

ELEVATION_ZONES = {
    "critical": (-99, 0),
    "very_high": (0, 2),
    "high": (2, 5),
    "medium": (5, 10),
    "low": (10, 25),
    "safe": (25, 9999),
}

TILE_REGISTRY = {
    "DEMNAS_1209-43": {
        "path": str(_DEFAULT_DEM_DIR / "DEMNAS_1209-43_v1.0.tif"),
        "bbox": {"lon_min": 106.50, "lon_max": 106.75, "lat_min": -6.25, "lat_max": -6.00},
        "origin": (106.50, -6.00),
        "pixel_deg": 7.500750075007501e-05,
        "width": 3333,
        "height": 3333,
        "strip_offset": None,
    },
    "DEMNAS_1209-44": {
        "path": str(_DEFAULT_DEM_DIR / "DEMNAS_1209-44_v1.0.tif"),
        "bbox": {"lon_min": 106.75, "lon_max": 107.00, "lat_min": -6.25, "lat_max": -6.00},
        "origin": (106.75, -6.00),
        "pixel_deg": 7.500750075007501e-05,
        "width": 3333,
        "height": 3333,
        "strip_offset": None,
    },
    "DEMNAS_1209-42": {
        "path": str(_DEFAULT_DEM_DIR / "DEMNAS_1209-42_v1.0.tif"),
        "bbox": {"lon_min": 106.75, "lon_max": 107.00, "lat_min": -6.50, "lat_max": -6.25},
        "origin": (106.75, -6.25),
        "pixel_deg": 7.500750075007501e-05,
        "width": 3333,
        "height": 3333,
        "strip_offset": None,
    },
}

_TIFF_TYPE_SIZES = {
    1: 1,   # BYTE
    2: 1,   # ASCII
    3: 2,   # SHORT
    4: 4,   # LONG
    11: 4,  # FLOAT
}
_TIFF_TYPE_FORMATS = {
    1: "B",
    2: "c",
    3: "H",
    4: "I",
    11: "f",
}

_dem_lock = threading.RLock()
_dem_cache: dict = {
    "initialized": False,
    "tiles": {},
    "available_tiles": 0,
}


def _detect_strip_offset(path: str | Path) -> dict:
    """
    Parse TIFF strip metadata with ``struct`` only.

    Returns a dict containing:
      * strip_offsets: tuple[int, ...]
      * strip_byte_counts: tuple[int, ...]
      * rows_per_strip: int
      * endian: "<" | ">"
      * parsed_width / parsed_height / bits_per_sample / sample_format / compression
    """
    resolved_path = Path(path)
    with resolved_path.open("rb") as fh:
        header = fh.read(8)
        if len(header) != 8:
            raise ValueError(f"Incomplete TIFF header: {resolved_path}")

        byte_order = header[:2]
        if byte_order == b"II":
            endian = "<"
        elif byte_order == b"MM":
            endian = ">"
        else:
            raise ValueError(f"Unsupported TIFF byte order for {resolved_path}: {byte_order!r}")

        magic = struct.unpack(f"{endian}H", header[2:4])[0]
        if magic != 42:
            raise ValueError(f"Unsupported TIFF magic for {resolved_path}: {magic}")

        ifd_offset = struct.unpack(f"{endian}I", header[4:8])[0]
        fh.seek(ifd_offset)
        entry_count_raw = fh.read(2)
        if len(entry_count_raw) != 2:
            raise ValueError(f"Incomplete IFD entry count for {resolved_path}")
        entry_count = struct.unpack(f"{endian}H", entry_count_raw)[0]

        tags: dict[int, tuple] = {}
        for _ in range(entry_count):
            entry_raw = fh.read(12)
            if len(entry_raw) != 12:
                raise ValueError(f"Truncated IFD entry for {resolved_path}")
            tag, field_type, count = struct.unpack(f"{endian}HHI", entry_raw[:8])
            values = _decode_ifd_values(
                fh,
                endian=endian,
                field_type=field_type,
                count=count,
                value_field=entry_raw[8:12],
            )
            tags[tag] = values

    strip_offsets = tuple(int(v) for v in (tags.get(273) or ()))
    strip_byte_counts = tuple(int(v) for v in (tags.get(279) or ()))
    rows_per_strip = int((tags.get(278) or (1,))[0])
    parsed_width = int((tags.get(256) or (0,))[0])
    parsed_height = int((tags.get(257) or (0,))[0])
    bits_per_sample = int((tags.get(258) or (0,))[0])
    compression = int((tags.get(259) or (1,))[0])
    sample_format = int((tags.get(339) or (0,))[0])

    if not strip_offsets:
        raise ValueError(f"StripOffsets tag missing or empty for {resolved_path}")
    if not strip_byte_counts:
        raise ValueError(f"StripByteCounts tag missing or empty for {resolved_path}")

    return {
        "strip_offsets": strip_offsets,
        "strip_byte_counts": strip_byte_counts,
        "rows_per_strip": rows_per_strip,
        "endian": endian,
        "parsed_width": parsed_width,
        "parsed_height": parsed_height,
        "bits_per_sample": bits_per_sample,
        "compression": compression,
        "sample_format": sample_format,
    }


def initialize_dem() -> dict:
    """Best-effort, idempotent DEM metadata initialiser."""
    with _dem_lock:
        if _dem_cache["initialized"]:
            return {
                "initialized": True,
                "available_tiles": _dem_cache["available_tiles"],
                "tiles": sorted(_dem_cache["tiles"].keys()),
            }

        prepared_tiles: dict[str, dict] = {}
        available_tiles = 0

        for tile_id, meta in TILE_REGISTRY.items():
            tile = dict(meta)
            tile["tile_id"] = tile_id
            tile["available"] = False
            tile["resolved_path"] = None
            tile["strip_offsets"] = ()
            tile["strip_byte_counts"] = ()
            tile["rows_per_strip"] = 1
            tile["endian"] = "<"

            resolved_path = _resolve_dem_path(str(meta.get("path") or ""))
            if resolved_path is None:
                _log.warning("DEM tile %s missing on disk: %s", tile_id, meta.get("path"))
                prepared_tiles[tile_id] = tile
                continue

            try:
                strip_info = _detect_strip_offset(resolved_path)
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    "DEM tile %s unavailable (%s: %s)",
                    tile_id,
                    type(exc).__name__,
                    exc,
                )
                tile["resolved_path"] = str(resolved_path)
                prepared_tiles[tile_id] = tile
                continue

            tile["resolved_path"] = str(resolved_path)
            tile["strip_offsets"] = strip_info["strip_offsets"]
            tile["strip_byte_counts"] = strip_info["strip_byte_counts"]
            tile["rows_per_strip"] = max(1, int(strip_info["rows_per_strip"]))
            tile["endian"] = str(strip_info["endian"])
            tile["strip_offset"] = int(strip_info["strip_offsets"][0])

            if strip_info["parsed_width"] and strip_info["parsed_width"] != int(tile["width"]):
                _log.warning(
                    "DEM tile %s width mismatch registry=%s parsed=%s",
                    tile_id,
                    tile["width"],
                    strip_info["parsed_width"],
                )
            if strip_info["parsed_height"] and strip_info["parsed_height"] != int(tile["height"]):
                _log.warning(
                    "DEM tile %s height mismatch registry=%s parsed=%s",
                    tile_id,
                    tile["height"],
                    strip_info["parsed_height"],
                )
            if strip_info["bits_per_sample"] and strip_info["bits_per_sample"] != 32:
                _log.warning(
                    "DEM tile %s unexpected BitsPerSample=%s",
                    tile_id,
                    strip_info["bits_per_sample"],
                )
            if strip_info["sample_format"] and strip_info["sample_format"] != 3:
                _log.warning(
                    "DEM tile %s unexpected SampleFormat=%s",
                    tile_id,
                    strip_info["sample_format"],
                )
            if strip_info["compression"] not in (0, 1):
                _log.warning(
                    "DEM tile %s unsupported compression=%s",
                    tile_id,
                    strip_info["compression"],
                )
            if len(tile["strip_offsets"]) < math.ceil(int(tile["height"]) / tile["rows_per_strip"]):
                _log.warning("DEM tile %s strip table shorter than expected.", tile_id)
            else:
                tile["available"] = True
                available_tiles += 1

            prepared_tiles[tile_id] = tile

        _dem_cache["tiles"] = prepared_tiles
        _dem_cache["available_tiles"] = available_tiles
        _dem_cache["initialized"] = True

        _log.info(
            "DEM initialised: available_tiles=%s total_tiles=%s",
            available_tiles,
            len(prepared_tiles),
        )
        return {
            "initialized": True,
            "available_tiles": available_tiles,
            "tiles": sorted(prepared_tiles.keys()),
        }


def get_elevation(lat: float, lon: float) -> dict:
    """Return point elevation metadata for ``(lat, lon)``."""
    point = _safe_point(lat, lon)
    if point is None:
        return _unknown_elevation()

    initialize_dem()
    tile = _find_tile(point[0], point[1])
    if tile is None:
        return _unknown_elevation()

    if not tile.get("available"):
        return _unknown_elevation(tile_id=tile["tile_id"])

    try:
        with open(tile["resolved_path"], "rb") as fh:
            row, col = _latlon_to_row_col(tile, point[0], point[1])
            if row is None or col is None:
                return _unknown_elevation(tile_id=tile["tile_id"])
            elevation_m = _read_pixel(tile, row, col, fh)
    except OSError as exc:
        _log.warning("DEM read failed for tile %s: %s", tile["tile_id"], exc)
        return _unknown_elevation(tile_id=tile["tile_id"])

    if elevation_m is None:
        return _unknown_elevation(tile_id=tile["tile_id"])

    return {
        "elevation_m": round(elevation_m, 3),
        "is_below_sea_level": bool(elevation_m < 0.0),
        "tile_id": tile["tile_id"],
        "source": DEM_SOURCE_NAME,
    }


def classify_flood_zone(elevation_m: float | None) -> str:
    """Classify elevation into a coarse flood-vulnerability zone."""
    if elevation_m is None:
        return "unknown"
    for zone_name, (low, high) in ELEVATION_ZONES.items():
        if low <= float(elevation_m) < high:
            return zone_name
    return "unknown"


def get_elevation_context(lat: float, lon: float, radius_px: int = 3) -> dict:
    """Return local 7x7 neighbourhood context around the point."""
    point = _safe_point(lat, lon)
    if point is None:
        return _unknown_context()

    initialize_dem()
    center_tile = _find_tile(point[0], point[1])
    if center_tile is None or not center_tile.get("available"):
        return _unknown_context()

    radius = max(1, int(radius_px))
    pixel_deg = float(center_tile["pixel_deg"])
    samples: list[tuple[int, int, float]] = []
    handles: dict[str, BinaryIO] = {}

    try:
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                sample_lat = point[0] - (dy * pixel_deg)
                sample_lon = point[1] + (dx * pixel_deg)
                sample = _sample_elevation(sample_lat, sample_lon, handles)
                if sample is not None:
                    samples.append((dy, dx, sample))
    finally:
        for handle in handles.values():
            handle.close()

    if not samples:
        return _unknown_context()

    center_value = next((value for dy, dx, value in samples if dy == 0 and dx == 0), None)
    values = [value for _, _, value in samples]
    min_elevation = min(values)
    max_elevation = max(values)

    if center_value is None:
        return _unknown_context()

    neighbors = [value for dy, dx, value in samples if not (dy == 0 and dx == 0)]
    local_minimum = bool(neighbors) and center_value <= (min(neighbors) + _FLOAT_TOLERANCE_M)
    relief = max(max_elevation - min_elevation, 0.0)
    depression_depth = max(0.0, (sum(neighbors) / len(neighbors)) - center_value) if neighbors else 0.0
    depression_score = 0.0 if relief <= 0.0 else min(1.0, depression_depth / relief)

    max_gradient = 0.0
    for dy, dx, neighbor_value in samples:
        if dy == 0 and dx == 0:
            continue
        distance_m = math.hypot(dx, dy) * pixel_deg * _METERS_PER_DEGREE
        if distance_m <= 0.0:
            continue
        gradient = abs(center_value - neighbor_value) / distance_m
        if gradient > max_gradient:
            max_gradient = gradient

    return {
        "elevation_m": round(center_value, 3),
        "min_elevation_m": round(min_elevation, 3),
        "max_elevation_m": round(max_elevation, 3),
        "slope_estimate": round(max_gradient, 6),
        "is_local_minimum": local_minimum,
        "depression_score": round(depression_score, 4),
        "sample_count": len(samples),
        "kernel_size": (radius * 2) + 1,
        "source": DEM_SOURCE_NAME,
    }


def estimate_flow_direction(lat: float, lon: float) -> dict:
    """Estimate D8 steepest-descent direction from the DEM."""
    point = _safe_point(lat, lon)
    if point is None:
        return _unknown_flow()

    initialize_dem()
    center_tile = _find_tile(point[0], point[1])
    if center_tile is None or not center_tile.get("available"):
        return _unknown_flow()

    pixel_deg = float(center_tile["pixel_deg"])
    center = get_elevation(point[0], point[1]).get("elevation_m")
    if center is None:
        return _unknown_flow()

    directions = {
        (-1, 0): "N",
        (-1, 1): "NE",
        (0, 1): "E",
        (1, 1): "SE",
        (1, 0): "S",
        (1, -1): "SW",
        (0, -1): "W",
        (-1, -1): "NW",
    }

    best_direction = None
    best_drop = 0.0
    best_gradient = 0.0
    handles: dict[str, BinaryIO] = {}

    try:
        for (dy, dx), label in directions.items():
            sample_lat = point[0] - (dy * pixel_deg)
            sample_lon = point[1] + (dx * pixel_deg)
            neighbor = _sample_elevation(sample_lat, sample_lon, handles)
            if neighbor is None:
                continue
            drop = center - neighbor
            distance_m = math.hypot(dx, dy) * pixel_deg * _METERS_PER_DEGREE
            if distance_m <= 0.0:
                continue
            gradient = drop / distance_m
            if gradient > best_gradient:
                best_gradient = gradient
                best_drop = drop
                best_direction = label
    finally:
        for handle in handles.values():
            handle.close()

    if best_direction is None or best_gradient <= 0.0:
        return {
            "flow_direction": "flat",
            "confidence": "low",
            "drop_m": 0.0,
            "slope": 0.0,
            "source": DEM_SOURCE_NAME,
        }

    if best_gradient >= 0.08:
        confidence = "high"
    elif best_gradient >= 0.02:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "flow_direction": best_direction,
        "confidence": confidence,
        "drop_m": round(best_drop, 3),
        "slope": round(best_gradient, 6),
        "source": DEM_SOURCE_NAME,
    }


def _decode_ifd_values(
    fh: BinaryIO,
    *,
    endian: str,
    field_type: int,
    count: int,
    value_field: bytes,
) -> tuple:
    item_size = _TIFF_TYPE_SIZES.get(field_type)
    item_format = _TIFF_TYPE_FORMATS.get(field_type)
    if item_size is None or item_format is None:
        return ()

    total_bytes = item_size * count
    if total_bytes <= 4:
        payload = value_field[:total_bytes]
    else:
        value_offset = struct.unpack(f"{endian}I", value_field)[0]
        current_pos = fh.tell()
        fh.seek(value_offset)
        payload = fh.read(total_bytes)
        fh.seek(current_pos)
        if len(payload) != total_bytes:
            return ()

    if field_type == 2:
        return tuple(payload.rstrip(b"\x00").decode("ascii", errors="ignore"))

    unpacked = struct.unpack(f"{endian}{count}{item_format}", payload)
    return tuple(unpacked)


def _resolve_dem_path(raw_path: str) -> Path | None:
    candidates: list[Path] = []
    if raw_path:
        candidates.append(Path(raw_path))
        candidates.append(Path(raw_path.replace("_v1_0.tif", "_v1.0.tif")))

        filename = Path(raw_path).name
        if filename:
            candidates.append(_DEFAULT_DEM_DIR / filename)
            candidates.append(_DEFAULT_DEM_DIR / filename.replace("_v1_0.tif", "_v1.0.tif"))

    seen: set[str] = set()
    for candidate in candidates:
        candidate_str = str(candidate)
        if candidate_str in seen:
            continue
        seen.add(candidate_str)
        try:
            if candidate.exists() and candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def _safe_point(lat: float, lon: float) -> tuple[float, float] | None:
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
        return None
    return lat_f, lon_f


def _find_tile(lat: float, lon: float) -> dict | None:
    tiles = _dem_cache.get("tiles") or {}
    for tile in tiles.values():
        bbox = tile["bbox"]
        within_lon = bbox["lon_min"] <= lon <= bbox["lon_max"]
        within_lat = bbox["lat_min"] <= lat <= bbox["lat_max"]
        if within_lon and within_lat:
            return tile
    return None


def _latlon_to_row_col(tile: dict, lat: float, lon: float) -> tuple[int | None, int | None]:
    bbox = tile["bbox"]
    if not (bbox["lon_min"] <= lon <= bbox["lon_max"] and bbox["lat_min"] <= lat <= bbox["lat_max"]):
        return None, None

    origin_lon, origin_lat = tile["origin"]
    pixel_deg = float(tile["pixel_deg"])
    width = int(tile["width"])
    height = int(tile["height"])

    col = int((lon - origin_lon) / pixel_deg)
    row = int((origin_lat - lat) / pixel_deg)

    if col == width and math.isclose(lon, bbox["lon_max"], abs_tol=pixel_deg):
        col = width - 1
    if row == height and math.isclose(lat, bbox["lat_min"], abs_tol=pixel_deg):
        row = height - 1

    if row < 0 or col < 0 or row >= height or col >= width:
        return None, None
    return row, col


def _read_pixel(tile: dict, row: int, col: int, fh: BinaryIO) -> float | None:
    rows_per_strip = max(1, int(tile["rows_per_strip"]))
    strip_index = row // rows_per_strip
    row_in_strip = row % rows_per_strip
    strip_offsets = tile["strip_offsets"]
    strip_byte_counts = tile["strip_byte_counts"]

    if strip_index >= len(strip_offsets):
        return None

    strip_offset = int(strip_offsets[strip_index])
    expected_bytes = ((row_in_strip * int(tile["width"])) + col + 1) * _FLOAT32_BYTES
    if strip_index < len(strip_byte_counts) and int(strip_byte_counts[strip_index]) < expected_bytes:
        return None

    byte_offset = strip_offset + (((row_in_strip * int(tile["width"])) + col) * _FLOAT32_BYTES)
    fh.seek(byte_offset)
    payload = fh.read(_FLOAT32_BYTES)
    if len(payload) != _FLOAT32_BYTES:
        return None

    value = struct.unpack(f"{tile['endian']}f", payload)[0]
    if not math.isfinite(value):
        return None
    if abs(value) > 10_000:
        return None
    return float(value)


def _sample_elevation(lat: float, lon: float, handles: dict[str, BinaryIO]) -> float | None:
    tile = _find_tile(lat, lon)
    if tile is None or not tile.get("available"):
        return None

    row, col = _latlon_to_row_col(tile, lat, lon)
    if row is None or col is None:
        return None

    path = str(tile["resolved_path"])
    handle = handles.get(path)
    if handle is None:
        try:
            handle = open(path, "rb")
        except OSError as exc:
            _log.warning("DEM sample read failed for tile %s: %s", tile["tile_id"], exc)
            return None
        handles[path] = handle
    return _read_pixel(tile, row, col, handle)


def _unknown_elevation(*, tile_id: str | None = None) -> dict:
    return {
        "elevation_m": None,
        "is_below_sea_level": False,
        "tile_id": tile_id,
        "source": DEM_SOURCE_NAME,
    }


def _unknown_context() -> dict:
    return {
        "elevation_m": None,
        "min_elevation_m": None,
        "max_elevation_m": None,
        "slope_estimate": None,
        "is_local_minimum": False,
        "depression_score": 0.0,
        "sample_count": 0,
        "kernel_size": 0,
        "source": DEM_SOURCE_NAME,
    }


def _unknown_flow() -> dict:
    return {
        "flow_direction": "unknown",
        "confidence": "low",
        "drop_m": 0.0,
        "slope": 0.0,
        "source": DEM_SOURCE_NAME,
    }


__all__ = [
    "DEM_SOURCE_NAME",
    "ELEVATION_ZONES",
    "TILE_REGISTRY",
    "_detect_strip_offset",
    "initialize_dem",
    "get_elevation",
    "classify_flood_zone",
    "get_elevation_context",
    "estimate_flow_direction",
]
