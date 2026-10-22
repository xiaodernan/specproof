"""#402 — the directory scan and the capsule-zip scan must agree on placeholders.

`scan_directory` and `scan_capsule_zips` each carried their own hand-copied
placeholder filter. They drifted: the zip scan was missing ``your-``,
``example``, and the canary secret, so the same content produced 1 finding as
a directory and 4 as a zip (3 false positives). A capsule is the artifact that
leaves the machine, so those false positives would fail a clean capsule.

These tests pin the invariant that matters: **for the same content, the two
scanners return the same findings** — every known placeholder is skipped by
both, and a real secret is still flagged by both.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from agent.security_scanner import scan_capsule_zips, scan_directory

PLACEHOLDER_LINES = [
    'api_key: "example-key-1234567890"',
    'api_key: "your-api-key-here"',
    'api_key: "your_api_key_here"',
    'api_key: "changeme-1234567890"',
    'api_key: "replace_me-1234567890"',
    'api_key: "demo_pass_1234567890"',
    'api_key: "demo-secret-1234567890"',
    'api_key: "test_pass_1234567890"',
    'api_key: "SPECPROOF_CANARY_a7f3b2c9d1e4_SECRET_DO_NOT_COMMIT"',
]

REAL_SECRET_LINE = 'api_key: "real-secret-abcdef123456"'


def _scan_both(tmp_path: Path, content: str) -> tuple[list[str], list[str]]:
    (tmp_path / "conf.txt").write_text(content, encoding="utf-8")
    dir_hits = sorted(f.matched_text for f in scan_directory(str(tmp_path)).findings)
    with zipfile.ZipFile(tmp_path / "capsule.zip", "w") as zf:
        zf.writestr("conf.txt", content)
    zip_hits = sorted(f.matched_text for f in scan_capsule_zips(str(tmp_path)))
    return dir_hits, zip_hits


def test_directory_and_zip_agree_on_the_same_content(tmp_path: Path) -> None:
    content = "\n".join([*PLACEHOLDER_LINES, REAL_SECRET_LINE]) + "\n"
    dir_hits, zip_hits = _scan_both(tmp_path, content)

    # positive control: the real secret is still flagged, so neither scanner
    # went silently blind (this test would otherwise be trivially green).
    assert len(dir_hits) == 1, f"expected only the real secret, got {dir_hits}"
    # the invariant: the two scanners must not disagree on the same content.
    assert dir_hits == zip_hits, (
        "directory and zip scans disagree on the same content: "
        f"dir={dir_hits} zip={zip_hits}"
    )


@pytest.mark.parametrize("line", PLACEHOLDER_LINES)
def test_each_placeholder_is_skipped_by_both(tmp_path: Path, line: str) -> None:
    dir_hits, zip_hits = _scan_both(tmp_path, line + "\n")
    assert dir_hits == [], f"directory flagged a placeholder: {dir_hits} ({line})"
    assert zip_hits == [], f"zip flagged a placeholder: {zip_hits} ({line})"


def test_real_secret_is_flagged_by_both(tmp_path: Path) -> None:
    dir_hits, zip_hits = _scan_both(tmp_path, REAL_SECRET_LINE + "\n")
    assert len(dir_hits) == 1, f"directory missed the real secret: {dir_hits}"
    assert len(zip_hits) == 1, f"zip missed the real secret: {zip_hits}"
