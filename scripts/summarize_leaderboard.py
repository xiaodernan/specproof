"""Summarize the raw SWE-bench leaderboard JSON into a Markdown table.

Reads docs/eval/swebench-leaderboard-raw.json (produced by
scripts/fetch_swebench_leaderboard.ps1), extracts the "Verified" leaderboard
view, and writes docs/eval/SWE_BENCH_LEADERBOARD.md with the top submissions
ranked by resolved percentage (agent, model, resolved %, cost, date).

Honesty contract: if the raw artifact is missing, malformed, or the upstream
page changed structure, the script writes a clearly marked FAILURE NOTE into
the output Markdown file and exits 1 instead of fabricating a table.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SOURCE_URL = "https://www.swebench.com"
VERIFIED_VIEW_NAME = "Verified"
DEFAULT_LIMIT = 15
EM_DASH = "\u2014"

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_PATH = REPO_ROOT / "docs" / "eval" / "swebench-leaderboard-raw.json"
DEFAULT_OUT_PATH = REPO_ROOT / "docs" / "eval" / "SWE_BENCH_LEADERBOARD.md"


class LeaderboardFormatError(ValueError):
    """Raised when the raw leaderboard artifact cannot be parsed honestly."""


@dataclass(frozen=True)
class LeaderboardRow:
    """A single submission row on one leaderboard view."""

    agent: str
    model: str
    resolved: float
    cost: float | None
    date: str | None


@dataclass(frozen=True)
class VerifiedView:
    """The parsed Verified view: ranked rows plus honest bookkeeping."""

    rows: tuple[LeaderboardRow, ...]
    total_submissions: int
    excluded_without_resolved: int


def _item_name(item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    name = item.get("name")
    return name if isinstance(name, str) else None


def _benchmark_items(blob: object) -> list[object]:
    if isinstance(blob, list):
        return blob
    # A single benchmark object ({"name": ..., "results": ...}) is also accepted.
    return [blob]


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _row_from_entry(entry: object) -> LeaderboardRow | None:
    if not isinstance(entry, dict):
        return None
    agent = _as_optional_str(entry.get("agent"))
    resolved = _as_float(entry.get("resolved"))
    if not agent or resolved is None:
        return None
    name = _as_optional_str(entry.get("name")) or ""
    display = _as_optional_str(entry.get("model_display")) or ""
    return LeaderboardRow(
        agent=agent,
        model=display or name,
        resolved=resolved,
        cost=_as_float(entry.get("cost")),
        date=_as_optional_str(entry.get("date")),
    )


def parse_verified_entries(blob: object) -> VerifiedView:
    """Extract and rank the Verified leaderboard rows from the raw blob."""
    items = _benchmark_items(blob)
    if not items:
        raise LeaderboardFormatError("the raw JSON is empty")
    names = [_item_name(item) or "(unnamed)" for item in items]
    verified = next(
        (
            item
            for item in items
            if (_item_name(item) or "").lower() == VERIFIED_VIEW_NAME.lower()
        ),
        None,
    )
    if verified is None:
        raise LeaderboardFormatError(
            "no 'Verified' leaderboard view found in the raw JSON "
            f"(top-level views: {', '.join(names)})"
        )
    if not isinstance(verified, dict):
        raise LeaderboardFormatError("the 'Verified' view is not an object")
    results = verified.get("results")
    if not isinstance(results, list):
        raise LeaderboardFormatError("the 'Verified' view has no 'results' array")
    rows: list[LeaderboardRow] = []
    excluded = 0
    for entry in results:
        row = _row_from_entry(entry)
        if row is None:
            excluded += 1
        else:
            rows.append(row)
    if not rows:
        raise LeaderboardFormatError(
            f"the 'Verified' view has {len(results)} entries but none carry "
            "a numeric 'resolved' percentage"
        )
    # Three-pass stable sort: resolved desc, then date desc, then agent asc.
    rows.sort(key=lambda r: r.agent.lower())
    rows.sort(key=lambda r: r.date or "", reverse=True)
    rows.sort(key=lambda r: r.resolved, reverse=True)
    return VerifiedView(
        rows=tuple(rows),
        total_submissions=len(results),
        excluded_without_resolved=excluded,
    )


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _format_cost(cost: float | None) -> str:
    if cost is None:
        return EM_DASH
    return "$" + format(cost, ",.2f")


def render_markdown(
    view: VerifiedView,
    limit: int,
    generated_at: str,
    fetched_at: str,
    raw_artifact: str,
    source_url: str = SOURCE_URL,
) -> str:
    """Render the top `limit` Verified rows as a Markdown table."""
    top = view.rows[:limit]
    lines = [
        "# SWE-bench Leaderboard (Verified)",
        "",
        f"> Fetched: {fetched_at} · Generated: {generated_at} · "
        f"Source: <{source_url}> (embedded leaderboard JSON).",
        f"> Raw artifact: `{raw_artifact}`.",
        f"> Verified view: {view.total_submissions} submissions; "
        f"table shows the top {len(top)} ranked by resolved %.",
        "> Cost is USD as reported by the submission; "
        f"{EM_DASH} means the site did not report a cost.",
        "",
        "| # | Agent | Model | Resolved % | Cost (USD) | Date |",
        "|---:|-------|-------|-----------:|-----------:|------|",
    ]
    for rank, row in enumerate(top, start=1):
        date = row.date if row.date else EM_DASH
        lines.append(
            f"| {rank} | {_escape_cell(row.agent)} | {_escape_cell(row.model)} | "
            f"{row.resolved:.1f} | {_format_cost(row.cost)} | {date} |"
        )
    if view.excluded_without_resolved:
        lines.append("")
        lines.append(
            f"> Note: {view.excluded_without_resolved} Verified submission(s) "
            "are excluded from the table (missing agent name or numeric resolved %)."
        )
    if len(view.rows) > limit:
        lines.append("")
        lines.append(
            f"> {len(view.rows) - limit} further submission(s) are below the top {limit}."
        )
    lines.append("")
    return "\n".join(lines)


def failure_note(reason: str, generated_at: str, raw_artifact: str) -> str:
    """Render the honest failure note used when parsing fails."""
    return "\n".join(
        [
            f"# SWE-bench Leaderboard {EM_DASH} Update Failed",
            "",
            f"> **FAILURE NOTE** {EM_DASH} generated {generated_at}. "
            "No leaderboard numbers in this file: nothing is fabricated.",
            "",
            "**What went wrong:**",
            "",
            reason,
            "",
            f"The summarizer could not parse the raw leaderboard artifact "
            f"`{raw_artifact}`. The upstream page may have changed structure, "
            "or the fetch step failed. Re-run:",
            "",
            "    powershell -File scripts/fetch_swebench_leaderboard.ps1",
            "    python scripts/summarize_leaderboard.py",
            "",
        ]
    )


def load_blob(raw_path: Path) -> object:
    try:
        text = raw_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LeaderboardFormatError(f"cannot read {raw_path}: {exc}") from exc
    try:
        parsed: object = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LeaderboardFormatError(f"{raw_path} is not valid JSON: {exc}") from exc
    return parsed


def _file_mtime_utc(path: Path) -> str:
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return "unknown"
    return datetime.fromtimestamp(stamp, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="summarize_leaderboard",
        description=(
            "Render the top Verified-view agents from the raw SWE-bench "
            "leaderboard JSON as a Markdown table."
        ),
    )
    parser.add_argument(
        "--raw",
        type=Path,
        default=DEFAULT_RAW_PATH,
        help="raw leaderboard JSON produced by scripts/fetch_swebench_leaderboard.ps1",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_PATH,
        help="output Markdown file (a FAILURE NOTE is written here on parse errors)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="number of top rows to include in the table (default: 15)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.limit < 1:
        print(f"error: --limit must be at least 1 (got {args.limit})", file=sys.stderr)
        return 2
    generated_at = now_utc()
    raw_name = args.raw.name
    try:
        fetched_at = _file_mtime_utc(args.raw)
        blob = load_blob(args.raw)
        view = parse_verified_entries(blob)
        markdown = render_markdown(
            view,
            limit=args.limit,
            generated_at=generated_at,
            fetched_at=fetched_at,
            raw_artifact=raw_name,
        )
        exit_code = 0
    except LeaderboardFormatError as exc:
        markdown = failure_note(str(exc), generated_at, raw_name)
        exit_code = 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markdown, encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
