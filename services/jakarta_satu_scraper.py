"""
Jakarta Satu dashboard scraper (DATA-1).

Scrapes three sections of the Jakarta Satu flood dashboard every hour:
  1. Data Pintu Air      — water gate readings (level cm + status)
  2. Daftar RT Terdampak — list of affected residential units
  3. Luas Wilayah Terdampak — total flooded area in km²

Architecture (separation of concerns for testability):
  scrape_raw()          — Selenium only; returns raw panel text strings
  parse_water_gates()   — pure function; testable without a browser
  parse_rt_impact()     — pure function; testable without a browser
  parse_area_impact()   — pure function; testable without a browser
  scrape_all()          — orchestrates scrape_raw + all parsers

Failure contract:
  Missing panel          → ScraperWarning logged + empty list; scrape continues
  Selenium crash/timeout → ScraperError raised (never swallowed); CLI exits non-zero
  Parse error            → empty results + warning; raw text always stored for replay
"""

from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from api.observability import get_logger

_log = get_logger("flood.jakarta_satu_scraper")

DASHBOARD_URL = (
    "https://jakartasatu.jakarta.go.id/portal/apps/dashboards/"
    "c2b19d6243dd4a2f80fa1e55481fdb11"
)

_PAGE_LOAD_WAIT_S = 15   # seconds to wait for JS rendering after page load
_DRIVER_TIMEOUT_S = 30   # Selenium page-load + implicit wait timeout

# ── Compiled patterns ─────────────────────────────────────────────────────────

_STATUS_RE = re.compile(
    r"\b(siaga\s*[1-4ivIV]+|normal|awas|bahaya|waspada|standby)\b",
    re.IGNORECASE,
)
_LEVEL_RE = re.compile(r"\b(\d{1,4})\s*(?:cm)?\b")
_RT_ID_RE = re.compile(r"\b(\d{1,3})\s*/\s*(\d{1,3})\b")
_AREA_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(?:km[²2]?)?\b", re.IGNORECASE)
_WILAYAH_RE = re.compile(
    r"jakarta\s+(barat|pusat|selatan|timur|utara)", re.IGNORECASE
)

# ── Domain types ──────────────────────────────────────────────────────────────


@dataclass
class WaterGateReading:
    gate_name: str
    water_level_cm: Optional[float]
    status: str
    raw_line: str


@dataclass
class AffectedRT:
    rt_identifier: str   # "NNN/NNN"
    kelurahan: str
    wilayah: str         # Jakarta Barat / Timur / etc.
    raw_line: str


@dataclass
class JakartaSatuSnapshot:
    scraped_at: datetime
    source_url: str
    scrape_duration_ms: int
    panels_found: int                  # 0–3
    water_gates: list[WaterGateReading]
    affected_rts: list[AffectedRT]
    flooded_area_km2: Optional[float]
    raw_water_gates_text: str
    raw_rt_impact_text: str
    raw_area_impact_text: str
    warnings: list[str]
    scrape_success: bool = True


# ── Pure parsers ──────────────────────────────────────────────────────────────


def parse_water_gates(text: str) -> tuple[list[WaterGateReading], list[str]]:
    """
    Parse water gate readings from raw panel text.

    Returns (readings, warnings). Never raises — on total failure returns
    ([], [warning]) so raw text is stored and can be re-parsed later.

    Typical text shape (one entry per name/level/status group):
        Data Pintu Air
        MANGGARAI
        850 cm
        Siaga 2
        KATULAMPA
        310 cm
        Normal
    """
    readings: list[WaterGateReading] = []
    warnings: list[str] = []

    if not text or not text.strip():
        warnings.append("parse_water_gates: empty panel text")
        return readings, warnings

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # Classify each line as "level", "status", or "name"
    classified: list[tuple[str, str]] = []
    for ln in lines:
        if _STATUS_RE.search(ln):
            classified.append(("status", ln))
        else:
            m = _LEVEL_RE.search(ln)
            if m and int(m.group(1)) < 3000 and len(ln) <= 20:
                classified.append(("level", ln))
            else:
                classified.append(("name", ln))

    _SKIP_KEYWORDS = {"pintu air", "tinggi", "status", "nama", "debit", "muka air"}

    i = 0
    while i < len(classified):
        label, ln = classified[i]
        if label != "name":
            i += 1
            continue
        if any(kw in ln.lower() for kw in _SKIP_KEYWORDS):
            i += 1
            continue

        gate_name = ln
        level_cm: Optional[float] = None
        status_str = "unknown"

        j = i + 1
        while j < len(classified) and j < i + 4:
            jlabel, jln = classified[j]
            if jlabel == "level" and level_cm is None:
                m = _LEVEL_RE.search(jln)
                if m:
                    level_cm = float(m.group(1))
                j += 1
            elif jlabel == "status" and status_str == "unknown":
                m = _STATUS_RE.search(jln)
                if m:
                    status_str = m.group(0).strip()
                j += 1
            else:
                break

        if level_cm is not None or status_str != "unknown":
            readings.append(WaterGateReading(
                gate_name=gate_name,
                water_level_cm=level_cm,
                status=status_str,
                raw_line=ln,
            ))
        i = j

    if not readings:
        warnings.append(
            f"parse_water_gates: no gate readings extracted from {len(lines)} lines"
        )
    return readings, warnings


def parse_rt_impact(text: str) -> tuple[list[AffectedRT], list[str]]:
    """
    Parse affected RT entries from raw panel text.

    Returns (affected_rts, warnings). Never raises.

    Typical text shape:
        Daftar RT Terdampak Banjir
        001/002 Cipinang Melayu Jakarta Timur
        003/001 Cawang Jakarta Timur
    """
    entries: list[AffectedRT] = []
    warnings: list[str] = []

    if not text or not text.strip():
        warnings.append("parse_rt_impact: empty panel text")
        return entries, warnings

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    for ln in lines:
        rt_match = _RT_ID_RE.search(ln)
        if not rt_match:
            continue

        rt_id = f"{rt_match.group(1).zfill(3)}/{rt_match.group(2).zfill(3)}"

        wilayah_match = _WILAYAH_RE.search(ln)
        wilayah = wilayah_match.group(0).title() if wilayah_match else ""

        if wilayah_match:
            kelurahan_raw = ln[rt_match.end(): wilayah_match.start()].strip()
        else:
            kelurahan_raw = ln[rt_match.end():].strip()

        kelurahan = re.sub(r"^[-–—,\s]+", "", kelurahan_raw)
        kelurahan = re.sub(r"^[Kk]el(?:urahan)?\.?\s*", "", kelurahan).strip()

        entries.append(AffectedRT(
            rt_identifier=rt_id,
            kelurahan=kelurahan,
            wilayah=wilayah,
            raw_line=ln,
        ))

    if not entries:
        warnings.append(
            f"parse_rt_impact: no RT entries extracted from {len(lines)} lines"
        )
    return entries, warnings


def parse_area_impact(text: str) -> tuple[Optional[float], list[str]]:
    """
    Parse total flooded area (km²) from raw panel text.

    Returns (area_km2_or_None, warnings). Never raises.
    """
    warnings: list[str] = []

    if not text or not text.strip():
        warnings.append("parse_area_impact: empty panel text")
        return None, warnings

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    for ln in lines:
        if any(kw in ln.lower() for kw in ("luas", "wilayah", "terdampak", "km")):
            # May still contain the number — extract it
            pass
        m = _AREA_RE.search(ln)
        if m:
            try:
                value = float(m.group(1).replace(",", "."))
                # Jakarta total area ≈ 661 km²; cap at 10_000 as sanity bound
                if 0 < value < 10_000:
                    return value, warnings
            except ValueError:
                continue

    warnings.append(
        f"parse_area_impact: no plausible area value found in {len(lines)} lines"
    )
    return None, warnings


# ── Selenium layer ────────────────────────────────────────────────────────────


class ScraperError(RuntimeError):
    """
    Unrecoverable scraper failure — Selenium crash, page-load timeout,
    or ChromeDriver initialisation failure.

    Never caught internally. The CLI exits non-zero when this propagates.
    """


class OutOfBandOnlyError(RuntimeError):
    """Raised when the Selenium scraper is invoked from the API process."""


def _is_api_process() -> bool:
    return "api.main" in sys.modules


def _build_driver():
    """Create a headless Chrome WebDriver. Raises ScraperError on any failure."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError as exc:
        raise ScraperError(
            "selenium is not installed — run: pip install 'selenium>=4.6.0'"
        ) from exc

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(_DRIVER_TIMEOUT_S)
        driver.implicitly_wait(5)
        return driver
    except Exception as exc:
        raise ScraperError(
            f"Chrome WebDriver initialisation failed: {exc}"
        ) from exc


def _extract_panel_text(driver, section_label: str) -> Optional[str]:
    """
    Find the calcite-panel whose text includes section_label and return its
    full text content. Returns None (with a warning) when not found.
    Missing panels are non-fatal — the caller stores None and logs a warning.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise ScraperError(
            "beautifulsoup4 is not installed — run: pip install beautifulsoup4"
        ) from exc

    soup = BeautifulSoup(driver.page_source, "html.parser")
    target = soup.find(string=lambda s: s and section_label in s)

    if target is None:
        _log.warning("jakarta_satu_panel_not_found", section_label=section_label)
        return None

    container = target.find_parent("calcite-panel")
    if container is None:
        # Fallback: nearest ancestor with substantial text content
        container = target.find_parent(
            lambda tag: tag.name in ("div", "section", "article")
            and len(tag.get_text()) > 50
        )

    if container is None:
        _log.warning("jakarta_satu_panel_container_missing", section_label=section_label)
        return None

    return container.get_text("\n", strip=True)


def scrape_raw(
    url: str = DASHBOARD_URL,
    wait_s: int = _PAGE_LOAD_WAIT_S,
) -> dict[str, Optional[str]]:
    """
    Load the dashboard and extract raw text from the three target panels.

    Returns dict with keys: water_gates, rt_impact, area_impact.
    Each value is a raw text string or None if the panel was not found.

    Raises ScraperError on Selenium / driver failures (never swallowed).
    """
    driver = _build_driver()
    try:
        _log.info("jakarta_satu_dashboard_loading", url=url)
        try:
            driver.get(url)
        except Exception as exc:
            raise ScraperError(f"Page load failed: {exc}") from exc

        _log.info("jakarta_satu_dashboard_waiting", wait_seconds=wait_s)
        time.sleep(wait_s)

        return {
            "water_gates": _extract_panel_text(driver, "Data Pintu Air"),
            "rt_impact": _extract_panel_text(driver, "Daftar RT Terdampak Banjir"),
            "area_impact": _extract_panel_text(
                driver,
                "Luas Wilayah Terdampak Banjir = Luas Area Seluruh RT Terdampak",
            ),
        }
    finally:
        driver.quit()


# ── Orchestration ─────────────────────────────────────────────────────────────


def scrape_all(
    url: str = DASHBOARD_URL,
    wait_s: int = _PAGE_LOAD_WAIT_S,
) -> JakartaSatuSnapshot:
    """
    Full pipeline: scrape + parse → JakartaSatuSnapshot.

    Raises ScraperError on fatal Selenium failure.
    Missing panels produce empty sub-lists + warnings, but do NOT raise.
    """
    # Selenium waits are intentionally kept out of the FastAPI process so the
    # scraper runs as a scheduled out-of-band job instead of a request handler.
    allow_runtime_scrape = os.getenv("FLOOD_ALLOW_RUNTIME_SCRAPE", "0")
    if allow_runtime_scrape != "1" or _is_api_process():
        execution_context = "api_process" if _is_api_process() else "runtime_scrape_disabled"
        _log.error(
            "jakarta_satu_scraper_out_of_band_only",
            execution_context=execution_context,
            allow_runtime_scrape=allow_runtime_scrape,
        )
        raise OutOfBandOnlyError(
            "jakarta_satu_scraper must run as a scheduled job outside the API process"
        )

    t0 = time.perf_counter()
    scraped_at = datetime.now(timezone.utc)

    raw = scrape_raw(url=url, wait_s=wait_s)

    duration_ms = round((time.perf_counter() - t0) * 1000)
    panels_found = sum(1 for v in raw.values() if v is not None)

    all_warnings: list[str] = []

    gates, gw = parse_water_gates(raw["water_gates"] or "")
    all_warnings.extend(gw)

    rts, rw = parse_rt_impact(raw["rt_impact"] or "")
    all_warnings.extend(rw)

    area_km2, aw = parse_area_impact(raw["area_impact"] or "")
    all_warnings.extend(aw)

    if all_warnings:
        _log.warning(
            "jakarta_satu_scrape_completed_with_warnings",
            warning_count=len(all_warnings),
            warnings=all_warnings,
        )
    else:
        _log.info(
            "Scrape OK — %d gate(s), %d RT(s), area=%.2f km², duration=%dms",
            water_gate_count=len(gates),
            affected_rt_count=len(rts),
            flooded_area_km2=area_km2 or 0.0,
            duration_ms=duration_ms,
        )

    return JakartaSatuSnapshot(
        scraped_at=scraped_at,
        source_url=url,
        scrape_duration_ms=duration_ms,
        panels_found=panels_found,
        water_gates=gates,
        affected_rts=rts,
        flooded_area_km2=area_km2,
        raw_water_gates_text=raw["water_gates"] or "",
        raw_rt_impact_text=raw["rt_impact"] or "",
        raw_area_impact_text=raw["area_impact"] or "",
        warnings=all_warnings,
        scrape_success=True,
    )


def run_ingest(
    url: str = DASHBOARD_URL,
    wait_s: int = _PAGE_LOAD_WAIT_S,
) -> JakartaSatuSnapshot:
    """Compatibility entry point for scheduled Jakarta Satu ingestion jobs."""
    return scrape_all(url=url, wait_s=wait_s)
