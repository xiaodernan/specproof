"""OpenAPI schema-diff gate (§8.1, §14 task 4 / GUIDE_GAP_AUDIT A-4).

Generates the current app.openapi() document and diffs it against a
committed baseline JSON (docs/openapi/baseline.json). Every endpoint
(method + path) and its response status codes are compared:

    + added endpoint     (in current, not in baseline)
    - removed endpoint   (in baseline, not in current)
    ~ changed endpoint   (same method+path, different response codes)

Exit codes:
    0 — no changes; or baseline was just created (first run, remember to
        commit it); or every change is exempted via --allow; or --update.
    1 — at least one blocking change (CI gate fails; update the baseline
        in the same PR when the change is intentional).
    2 — usage error or the API app could not be imported.

Usage:
    python scripts/openapi_diff.py docs/openapi/baseline.json
    python scripts/openapi_diff.py docs/openapi/baseline.json \
        --allow "GET /jobs/{job_id}/cancel:409, POST /jobs/v2"
    python scripts/openapi_diff.py docs/openapi/baseline.json --update

--allow tokens are comma-separated "METHOD /path" (exempts the whole
endpoint) or "METHOD /path:status" (exempts one added/removed response
code line); METHOD may be "*" for every method of a path.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import api.server  # noqa: E402  (imports the app; also enforces the config guard)

HTTP_METHODS = frozenset({
    "get", "post", "put", "patch", "delete", "head", "options", "trace",
})


def _operations(spec: dict[str, Any]) -> dict[str, set[str]]:
    """Extract {METHOD /path: {response codes}} from an OpenAPI document."""
    ops: dict[str, set[str]] = {}
    for path, item in spec.get("paths", {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method not in HTTP_METHODS or not isinstance(op, dict):
                continue
            responses = op.get("responses", {})
            ops[f"{method.upper()} {path}"] = {
                str(code) for code in responses if isinstance(responses, dict)
            }
    return ops


def _diff(
    baseline: dict[str, set[str]], current: dict[str, set[str]],
) -> tuple[list[str], list[str], list[tuple[str, list[str], list[str]]]]:
    """Return (added, removed, changed) where changed = (op, removed, added)."""
    added = sorted(set(current) - set(baseline))
    removed = sorted(set(baseline) - set(current))
    changed: list[tuple[str, list[str], list[str]]] = []
    for op in sorted(set(current) & set(baseline)):
        old_codes, new_codes = baseline[op], current[op]
        if old_codes != new_codes:
            changed.append((
                op,
                sorted(old_codes - new_codes),
                sorted(new_codes - old_codes),
            ))
    return added, removed, changed


def _parse_allow(raw: str | None) -> set[tuple[str, str, str | None]]:
    """Parse --allow tokens into {(method, path, status-or-None)}."""
    allowed: set[tuple[str, str, str | None]] = set()
    if not raw:
        return allowed
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        parts = token.split()
        if len(parts) != 2:
            raise ValueError(
                f"allow token must be 'METHOD /path[:status]', got: {token!r}"
            )
        method = parts[0].upper()
        path_status = parts[1]
        if ":" in path_status:
            path, status = path_status.rsplit(":", 1)
        else:
            path, status = path_status, None
        allowed.add((method, path, status))
    return allowed


def _exempt(
    op: str, status: str | None, allowed: set[tuple[str, str, str | None]],
) -> bool:
    method, _, path = op.partition(" ")
    return (
        (method, path, None) in allowed
        or ("*", path, None) in allowed
        or (status is not None and (
            (method, path, status) in allowed or ("*", path, status) in allowed
        ))
    )


def _report(
    added: list[str],
    removed: list[str],
    changed: list[tuple[str, list[str], list[str]]],
    allowed: set[tuple[str, str, str | None]],
) -> bool:
    """Print the diff report; return True when anything is blocking."""
    blocking = False
    lines: list[tuple[str, str]] = []  # (text, kind)
    for op in added:
        lines.append((f"+ {op}", op))
    for op in removed:
        lines.append((f"- {op}", op))
    for op, old_codes, new_codes in changed:
        for code in old_codes:
            lines.append((f"~ {op} response {code} removed", op + "|" + code))
        for code in new_codes:
            lines.append((f"~ {op} response {code} added", op + "|" + code))
    if not lines:
        print("[openapi-diff] no schema changes — gate passes.")
        return False
    for text, key in lines:
        if " " not in key:
            status = None
        elif key.count("|") == 1:
            op, status = key.split("|")
        else:
            op, status = key, None
        if _exempt(op, status, allowed):
            print(f"[openapi-diff] allowed (--allow): {text}")
        else:
            print(f"[openapi-diff] BLOCKING: {text}")
            blocking = True
    return blocking


def _load_or_write_baseline(path: Path, spec: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Return (created, baseline_doc). Creates the file on first run."""
    if path.exists():
        return False, json.loads(path.read_text(encoding="utf-8"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    print(
        f"[openapi-diff] baseline did not exist; created {path} "
        "(first run — commit this file so CI has a baseline)."
    )
    return True, spec


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenAPI schema diff gate")
    parser.add_argument(
        "baseline", help="committed baseline JSON (e.g. docs/openapi/baseline.json)",
    )
    parser.add_argument(
        "--allow",
        default=None,
        help="comma-separated 'METHOD /path[:status]' exemptions",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="regenerate the baseline from the current schema (reviewed change)",
    )
    args = parser.parse_args(argv)
    try:
        allowed = _parse_allow(args.allow)
    except ValueError as exc:
        print(f"[openapi-diff] error: {exc}", file=sys.stderr)
        return 2

    try:
        spec = api.server.app.openapi()
    except Exception as exc:  # noqa: BLE001 — report import-time failures clearly
        print(f"[openapi-diff] error: could not generate OpenAPI schema: {exc}", file=sys.stderr)
        return 2

    baseline_path = Path(args.baseline)
    created, baseline_doc = _load_or_write_baseline(baseline_path, spec)
    if created or args.update:
        if not created:
            baseline_path.write_text(
                json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"[openapi-diff] baseline updated at {baseline_path} (--update).")
        return 0

    added, removed, changed = _diff(
        _operations(baseline_doc), _operations(spec),
    )
    return 1 if _report(added, removed, changed, allowed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
