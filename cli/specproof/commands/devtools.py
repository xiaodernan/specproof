"""specproof devtools — deterministic developer tools (DevMind capability port).

Commands:
    specproof devtools quality PATH    code-quality analysis (score/smells)
    specproof devtools docs PATH       generate API/README markdown
    specproof devtools archreview PATH architecture review (cycles/layers)

Honesty rules:
- Python-only analysis; other languages are reported as not_supported.
- No LLM, no network: every number is derived deterministically from source.
- Layer rules for archreview are opt-in via --layer and --allow options;
  without them no layering violation is ever fabricated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click


def _resolve(path: str) -> Path:
    target = Path(path)
    if not target.exists():
        raise click.ClickException(f"path does not exist: {path}")
    return target


def _emit(report: dict[str, Any], output: str | None, as_json: bool) -> None:
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if output:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        click.echo(f"report written to: {output}")
        return
    if as_json:
        click.echo(payload, nl=False)
    else:
        click.echo(json.dumps(report, ensure_ascii=False, indent=2))


@click.group("devtools")
def devtools_cmd() -> None:
    """Deterministic developer tools (quality / docs / archreview)."""


@devtools_cmd.command("quality")
@click.argument("path", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, help="print the JSON report")
@click.option("--output", "-o", default=None, help="write report to this file")
def quality_cmd(path: str, as_json: bool, output: str | None) -> None:
    """Analyze code quality of a Python file or directory."""
    from devtools.quality import analyze

    report = analyze(_resolve(path))
    summary = report["summary"]
    click.echo(
        f"files={summary['file_count']} lines={summary['total_lines']} "
        f"functions={summary['function_count']} classes={summary['class_count']} "
        f"issues={summary['issue_count']} avg_score={summary['avg_score']}/10"
    )
    if as_json or output:
        _emit(report, output, as_json)


@devtools_cmd.command("docs")
@click.argument("path", type=click.Path(exists=True))
@click.option("--type", "doc_type", default="readme",
              type=click.Choice(["readme", "api"], case_sensitive=False),
              help="document type to generate (readme | api)")
@click.option("--output", "-o", default=None, help="output markdown file")
def docs_cmd(path: str, doc_type: str, output: str | None) -> None:
    """Generate deterministic markdown docs from Python source."""
    from devtools.docs import generate

    content, file_name = generate(_resolve(path), doc_type)
    out_path = Path(output) if output else Path.cwd() / file_name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    click.echo(f"generated {doc_type} docs ({len(content)} chars) -> {out_path}")


@devtools_cmd.command("archreview")
@click.argument("path", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, help="print the JSON report")
@click.option("--output", "-o", default=None, help="write report to this file")
@click.option("--layer", "layers", multiple=True, default=None,
              metavar="REGEX=NAME", help="layer rule: module regex -> layer name")
@click.option("--allow", "allows", multiple=True, default=None,
              metavar="SRC>DST", help="allowed layer edge (repeatable)")
def archreview_cmd(
    path: str,
    as_json: bool,
    output: str | None,
    layers: tuple[str, ...],
    allows: tuple[str, ...],
) -> None:
    """Review architecture: import cycles, hubs and optional layer rules."""
    from devtools.archreview import review

    layer_rules: dict[str, str] = {}
    for item in layers:
        if "=" not in item:
            raise click.ClickException(f"invalid --layer: {item} (want REGEX=NAME)")
        pattern, name = item.split("=", 1)
        layer_rules[pattern] = name
    allowed_edges: list[tuple[str, str]] = []
    for item in allows:
        if ">" not in item:
            raise click.ClickException(f"invalid --allow: {item} (want SRC>DST)")
        src_layer, dst_layer = item.split(">", 1)
        allowed_edges.append((src_layer, dst_layer))
    report = review(_resolve(path), layer_rules or None, allowed_edges)
    click.echo(
        f"modules={report['module_count']} edges={report['edge_count']} "
        f"cycles={len(report['cycles'])} findings={len(report['findings'])}"
    )
    if as_json or output:
        _emit(report, output, as_json)
