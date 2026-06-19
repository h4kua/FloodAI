"""
Phase 5 - CI guard against `_deprecated.*` imports.

Anything quarantined into `_deprecated/` is dead code preserved on disk for
emergency rollback only. Production code MUST NOT import from there. This test
fails if a future PR re-introduces a dependency on the quarantine.

Scope: scans every `.py` under `app/`, `db/`, `scripts/`, and `tests/`
(excluding the quarantine directory itself). Static text scan - does not
execute any imports.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = ("app", "db", "scripts", "tests")
EXCLUDE_DIRS = {"_deprecated", "__pycache__", ".venv", "flood_env", ".git"}

# Match either `from _deprecated.foo import ...` or `import _deprecated.foo`
# at the start of a non-comment line.
_BAD_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+_deprecated(?:\.|\s)|import\s+_deprecated(?:\.|\s|$))",
    re.MULTILINE,
)


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root_name in SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune excluded directories in-place so os.walk doesn't descend.
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
            for fname in filenames:
                if fname.endswith(".py"):
                    files.append(Path(dirpath) / fname)
    return files


def test_no_imports_target_quarantine_directory():
    """
    No Python file under app/, db/, scripts/, tests/ may import from
    `_deprecated.*`. Files there are dead-code quarantine - see
    `_deprecated/README.md` for the rollback path.
    """
    offenders: list[tuple[str, int, str]] = []
    for path in _iter_python_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in _BAD_IMPORT_RE.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            offending_line = text.split("\n")[line_no - 1].strip()
            offenders.append((str(path.relative_to(REPO_ROOT)), line_no, offending_line))

    if offenders:
        msg = "Forbidden imports of _deprecated.* found:\n" + "\n".join(
            f"  {path}:{ln}  {src}" for path, ln, src in offenders
        )
        pytest.fail(msg)


# NOTE: the former `test_quarantine_directory_exists` was removed — the
# `_deprecated/` quarantine has been fully cleaned up, so asserting that the
# scaffolding still exists is obsolete. The import-guard above remains valid
# (it simply finds no offenders) and protects against re-introducing a
# dependency on a quarantine directory if one is ever recreated.
