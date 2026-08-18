"""M1 task understanding and spec parsing (design doc §4.1).

Three input forms are normalized into one TaskSpec:
  1. plain-text task description — deterministic rules: the first body line
     becomes the title, remaining lines join into the description; lines with
     the "验收:" / "禁止:" / "影响:" prefixes are split into the matching
     fields instead;
  2. structured JSON — validated field by field: a missing field or a wrong
     type raises a clear error naming the field;
  3. an existing spec file (.md/.txt/.json/.spec) — routed by extension /
     content into one of the two parsers above; a missing file path is a
     clear error.

Determinism contract: identical input -> identical TaskSpec; no model calls.
Unknown JSON keys are ignored (the schema is shared with SpecProof verify,
which may carry extra fields).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_REQUIRED_FIELDS: tuple[str, ...] = (
    "title",
    "description",
    "acceptance_criteria",
    "forbidden_changes",
    "affected_area_hint",
)
_SPEC_FILE_SUFFIXES: tuple[str, ...] = (".md", ".txt", ".json", ".spec")


class SpecParseError(ValueError):
    """Task spec input could not be parsed deterministically."""


@dataclass(frozen=True)
class TaskSpec:
    """Normalized task spec — same shape feeds craft (build) and verify (accept)."""

    title: str
    description: str
    acceptance_criteria: list[str] = field(default_factory=list)
    forbidden_changes: list[str] = field(default_factory=list)
    affected_area_hint: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "description": self.description,
            "acceptance_criteria": list(self.acceptance_criteria),
            "forbidden_changes": list(self.forbidden_changes),
            "affected_area_hint": self.affected_area_hint,
        }


def parse_spec_text(text: str) -> TaskSpec:
    """Deterministic plain-text parse (prefix rules, no model).

    Rules: blank lines are dropped; the first remaining line is the title;
    "验收:"/"禁止:"/"影响:" prefixed lines go to their fields (prefix
    stripped); every other line joins the description.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    body: list[str] = []
    acceptance: list[str] = []
    forbidden: list[str] = []
    hints: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("验收:"):
            acceptance.append(line[len("验收:") :].strip())
        elif line.startswith("禁止:"):
            forbidden.append(line[len("禁止:") :].strip())
        elif line.startswith("影响:"):
            hints.append(line[len("影响:") :].strip())
        else:
            body.append(line)
    if not body:
        raise SpecParseError("spec 文本为空: 无法提取 title/description")
    return TaskSpec(
        title=body[0],
        description="\n".join(body[1:]),
        acceptance_criteria=acceptance,
        forbidden_changes=forbidden,
        affected_area_hint=",".join(hints),
    )


def parse_spec_json(data: object) -> TaskSpec:
    """Strict per-field JSON validation (design §4.1)."""
    if not isinstance(data, dict):
        raise SpecParseError("spec JSON 顶层必须是对象 (object)")
    for field_name in _REQUIRED_FIELDS:
        if field_name not in data:
            raise SpecParseError(f"spec JSON 缺少必填字段 '{field_name}'")
    title = data["title"]
    if not isinstance(title, str):
        raise SpecParseError("spec JSON 字段 'title' 类型错误: 应为字符串")
    if not title.strip():
        raise SpecParseError("spec JSON 字段 'title' 不能为空字符串")
    description = data["description"]
    if not isinstance(description, str):
        raise SpecParseError("spec JSON 字段 'description' 类型错误: 应为字符串")

    def _string_list(field: str, value: object) -> list[str]:
        if not isinstance(value, list):
            raise SpecParseError(f"spec JSON 字段 '{field}' 类型错误: 应为字符串数组")
        result: list[str] = []
        for index, item in enumerate(value):
            if not isinstance(item, str):
                raise SpecParseError(
                    f"spec JSON 字段 '{field}[{index}]' 类型错误: 应为字符串"
                )
            result.append(item)
        return result

    acceptance = _string_list("acceptance_criteria", data["acceptance_criteria"])
    forbidden = _string_list("forbidden_changes", data["forbidden_changes"])
    hint = data["affected_area_hint"]
    if not isinstance(hint, str):
        raise SpecParseError("spec JSON 字段 'affected_area_hint' 类型错误: 应为字符串")
    return TaskSpec(
        title=title,
        description=description,
        acceptance_criteria=acceptance,
        forbidden_changes=forbidden,
        affected_area_hint=hint,
    )


def parse_spec_file(path: str | Path) -> TaskSpec:
    """Parse an existing spec file; a missing file is a clear error."""
    file_path = Path(path)
    if not file_path.is_file():
        raise SpecParseError(f"spec 文件不存在: {file_path}")
    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SpecParseError(f"spec 文件无法读取 ({file_path}): {exc}") from exc
    if file_path.suffix.lower() == ".json" or content.lstrip().startswith("{"):
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise SpecParseError(f"spec JSON 文件解析失败 ({file_path}): {exc}") from exc
        return parse_spec_json(data)
    return parse_spec_text(content)


def parse_spec(source: str, *, cwd: Path | None = None) -> TaskSpec:
    """Unified entry: file path (existing) -> file parse; spec-file-like path
    that does not exist -> clear error; JSON literal -> strict JSON parse;
    anything else -> deterministic text parse."""
    if not source or not source.strip():
        raise SpecParseError("spec 输入为空")
    candidate = Path(source)
    if not candidate.is_absolute() and cwd is not None:
        candidate = Path(cwd) / candidate
    if candidate.is_file():
        return parse_spec_file(candidate)
    if candidate.suffix.lower() in _SPEC_FILE_SUFFIXES:
        raise SpecParseError(f"spec 文件不存在: {source}")
    stripped = source.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise SpecParseError(f"spec 文本以 '{{' 开头但 JSON 解析失败: {exc}") from exc
        return parse_spec_json(data)
    return parse_spec_text(source)
