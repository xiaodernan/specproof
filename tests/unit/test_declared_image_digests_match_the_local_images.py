"""The image an adapter says it ran is a claim; this pins it to the image on disk.

Three declarations carry the same fact — ``JavaMavenAdapter.IMAGE_DIGEST``, the
``COMPATIBILITY_MATRIX`` row derived from it, and the digest printed in
``docs/architecture/EXECUTION_COMPATIBILITY.md`` — and none of them was checked
against a real image. Measured (#499):

* ``maven:3.9-eclipse-temurin-21`` declared ``sha256:c07f7ccf…`` (labelled
  "2026-08-18 本机验证值") while ``docker image inspect`` on this host reports
  ``sha256:99e61abc…`` — the tag was re-pushed upstream (image built
  2026-09-26) and the pin went stale without anything noticing.
* the other four images matched exactly, which is what makes the one mismatch
  a signal rather than noise.

A digest is a *measurement*: the run resolves a TAG, so whatever that tag
resolves to is what ran. A constant that is never compared with the tag is a
claim that can silently stop being true.

When an image is not present locally the check is SKIPPED with a reason, never
silently passed — a machine without the images proves nothing either way.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from experiments.adapters import (
    COMPATIBILITY_MATRIX,
    GoAdapter,
    GradleAdapter,
    JavaMavenAdapter,
    NodeAdapter,
    PythonAdapter,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MATRIX_DOC = _REPO_ROOT / "docs" / "architecture" / "EXECUTION_COMPATIBILITY.md"

# (language, build_tool) in the matrix -> the adapter that backs that row.
_ROWS: dict[tuple[str, str], Any] = {
    ("Java", "Maven"): JavaMavenAdapter,
    ("Java", "Gradle"): GradleAdapter,
    ("JavaScript/TypeScript", "npm"): NodeAdapter,
    ("Python", "pip"): PythonAdapter,
    ("Go", "go"): GoAdapter,
}


def _local_repo_digests(image: str) -> tuple[str, ...] | None:
    """RepoDigests for ``image`` on this host, or None when it is not inspectable."""
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", image, "--format", "{{json .RepoDigests}}"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    digests = re.findall(r"sha256:[0-9a-f]{64}", proc.stdout)
    return tuple(digests)


def _doc_rows() -> dict[tuple[str, str], dict[str, str]]:
    lines = _MATRIX_DOC.read_text(encoding="utf-8").split("\n")
    start = next(
        (i for i, line in enumerate(lines) if line.strip().startswith("|") and "状态" in line),
        None,
    )
    assert start is not None, "the compatibility table is missing from the matrix doc"
    def cells(line: str) -> list[str]:
        # Escaped pipes (\|) inside a cell are content, not separators.
        return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]

    header = cells(lines[start])
    rows: dict[tuple[str, str], dict[str, str]] = {}
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            break
        values = cells(stripped)
        if all(set(v) <= {"-", ":"} and v for v in values):
            continue
        rows[(values[0], values[1])] = dict(zip(header, values, strict=False))
    return rows


def test_every_declared_digest_is_the_one_the_tag_resolves_to() -> None:
    stale: list[str] = []
    checked = 0
    for key, adapter in _ROWS.items():
        declared = getattr(adapter, "IMAGE_DIGEST", None)
        if not isinstance(declared, str):
            continue
        local = _local_repo_digests(adapter.IMAGE)
        if local is None:
            continue
        checked += 1
        if declared not in local:
            stale.append(
                f"{key[0]}/{key[1]}: declares {declared} but {adapter.IMAGE} resolves to "
                f"{', '.join(local) or '<none>'} — re-pull the image, re-verify, then update "
                "the constant (the pin describes what the tag resolves to, not what it used to)"
            )
    if checked == 0:
        pytest.skip("no adapter image is present locally — nothing to compare against")
    assert not stale, "; ".join(stale)


def test_a_row_without_a_digest_never_prints_one() -> None:
    """No declared digest means the cell must say so, not invent a fingerprint."""
    rows = _doc_rows()
    offenders: list[str] = []
    for key, adapter in _ROWS.items():
        if isinstance(getattr(adapter, "IMAGE_DIGEST", None), str):
            continue
        cell = rows[key]["镜像 (digest)"]
        if "sha256:" in cell:
            offenders.append(f"{key[0]}/{key[1]} prints a sha256 it never verified")
        if "未钉" not in cell:
            offenders.append(f"{key[0]}/{key[1]} does not say the digest is unpinned")
    assert not offenders, "; ".join(offenders)


def test_the_doc_prints_the_digest_the_matrix_carries() -> None:
    """Code matrix -> doc: a re-pinned digest must reach the reader-facing table."""
    rows = _doc_rows()
    matrix = {(row.language, row.build_tool): row for row in COMPATIBILITY_MATRIX}

    offenders: list[str] = []
    for key, row in matrix.items():
        cell = rows[key]["镜像 (digest)"]
        if row.image not in cell:
            offenders.append(f"{key[0]}/{key[1]}: doc does not name image {row.image!r}")
        if row.image_digest != "—" and row.image_digest not in cell:
            offenders.append(
                f"{key[0]}/{key[1]}: doc does not carry digest {row.image_digest[:19]}…"
            )
    assert not offenders, "; ".join(offenders)


def test_the_doc_prints_the_toolchain_the_adapter_declares() -> None:
    """The toolchain cell is copied by hand; copy it exactly."""
    rows = _doc_rows()
    offenders: list[str] = []
    for key, adapter in _ROWS.items():
        documented = rows[key]["工具链版本"].replace("\\|", "|")
        if documented != adapter.TOOLCHAIN:
            offenders.append(
                f"{key[0]}/{key[1]}: doc says {documented!r}, adapter declares "
                f"{adapter.TOOLCHAIN!r}"
            )
    assert not offenders, "; ".join(offenders)
