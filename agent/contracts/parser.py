"""P2 — Structured requirement parser.

Turns a free-text requirement specification into structured Requirement
objects: id, statement, acceptance criteria, forbidden changes, priority.
The deterministic section parser runs first; an optional LLM pass can
enrich sparse results (same degradation contract as compile_contracts).

Output is schema-validated: downstream stages must never guess what the
requirement means beyond what this parser extracted.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from pydantic import BaseModel, Field


class AcceptanceCriterion(BaseModel):
    """One machine-checkable acceptance condition."""

    id: str
    text: str
    kind: str = "behavioral"  # behavioral | security | compatibility | performance


class Requirement(BaseModel):
    """A structured requirement extracted from the spec."""

    id: str = Field(min_length=1, max_length=64)
    title: str = ""
    statement: str
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    priority: str = "P1"  # P1 (must) | P2 (should) | P3 (nice)
    source: str = "spec"


class ParseResult(BaseModel):
    requirements: list[Requirement] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    llm_enriched: bool = False


_SECTION_RE = re.compile(
    # Section title = the label before the colon / end of header line
    # ("1. Authentication"). A lookahead (not a consume) keeps everything
    # after the colon in the body, so requirement text is never swallowed.
    r"(?im)^\s*(?:#{1,6}\s*)?(?P<title>\d+\.\s*[^:\n]{0,80})(?=:|\s*$)"
)

_AC_RE = re.compile(
    # Lines carrying a modal verb ("... must ..."), bullet or prose style.
    # The verb may appear mid-sentence in requirement specs.
    r"(?im)^\s*(?:[-*]\s*)?"
    r"(?P<criterion>[^\n]*\b(?:must|must not|should|should not|shall)"
    r"\b[^\n]{0,300})\s*$"
)

_FORBIDDEN_RE = re.compile(
    r"(?im)(?:must not|must never|shall not|禁止|forbidden(?: to)?|no longer)[^\n.:]{0,160}"
)

_PRIORITY_RE = re.compile(r"(?i)\b(must|mandatory|required|critical)\b")


def _normalize_id(title: str, index: int) -> str:
    """REQ-01 style id derived from the section title or index."""
    if title:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-")[:24]
        return f"REQ-{slug.upper()}"
    return f"REQ-{index:02d}"


def parse_requirements(text: str) -> ParseResult:
    """Deterministic structured parse of a requirement specification.

    Sections ("1. Title" / "## Title") become requirements; bullet lines
    starting with must/should/shall become acceptance criteria; forbidden
    phrasing is captured as forbidden_changes.
    """
    warnings: list[str] = []
    if not text.strip():
        warnings.append("Empty requirement text — nothing to parse")
        return ParseResult(requirements=[], warnings=warnings)

    sections: list[tuple[str, str]] = []
    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        # No numbered sections: treat the whole text as one requirement.
        sections = [("Overall requirement", text)]
    else:
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].lstrip(": \t\r\n")
            sections.append((m.group("title").strip(), body))
        # Text before the first section header is a preamble: append it
        # AFTER the first section body so it never shadows the section's own
        # statement line.
        if matches[0].start() > 0:
            preamble = text[:matches[0].start()].strip()
            if preamble:
                sections[0] = (sections[0][0], sections[0][1] + "\n" + preamble)

    requirements: list[Requirement] = []
    for index, (title, body) in enumerate(sections, start=1):
        criteria = [
            AcceptanceCriterion(
                id=f"AC-{index:02d}-{j}",
                text=m.group("criterion").strip(),
            )
            for j, m in enumerate(_AC_RE.finditer(body), start=1)
        ]
        forbidden = [m.group(0).strip() for m in _FORBIDDEN_RE.finditer(body)]
        statement = body.strip().split("\n")[0][:300] if body.strip() else title
        priority = "P1" if _PRIORITY_RE.search(body) else "P2"
        requirements.append(Requirement(
            id=_normalize_id(title, index),
            title=title,
            statement=statement,
            acceptance_criteria=criteria,
            forbidden_changes=forbidden,
            priority=priority,
        ))

    return ParseResult(requirements=requirements, warnings=warnings)


_LLM_PARSE_PROMPT = """You are a requirements analyst. Parse the specification below
into structured requirements.

Return a JSON array of objects, each with:
- id: short unique id like REQ-AUTH-01
- title: short title
- statement: the requirement in one sentence
- acceptance_criteria: array of {id, text, kind} — concrete testable conditions
  (kind is one of behavioral/security/compatibility/performance)
- forbidden_changes: array of strings — changes that must NOT happen
- priority: P1 / P2 / P3

Specification:
{spec_text}

Return ONLY the JSON array."""


async def llm_enrich_requirements(text: str, provider: Any) -> list[Requirement]:
    """LLM parse with schema validation. Returns [] on any failure."""
    from providers.base import LLMMessage

    try:
        response = await provider.chat(
            messages=[LLMMessage(
                role="user",
                content=_LLM_PARSE_PROMPT.format(spec_text=text[:6000]),
            )],
            timeout=90.0,
        )
        content = response.content or ""
        start = content.find("[")
        end = content.rfind("]") + 1
        if start < 0 or end <= start:
            return []
        parsed = json.loads(content[start:end])
        return [Requirement.model_validate(item) for item in parsed]
    except Exception:
        return []


def parse_with_llm_fallback(
    text: str, provider: Any | None = None,
) -> ParseResult:
    """Deterministic parse, enriched by LLM when a provider is configured.

    The deterministic result is NEVER discarded: LLM output only replaces
    it when it validates against the schema AND carries at least as much
    information (>= criteria count).
    """
    result = parse_requirements(text)
    if provider is None:
        return result
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run, llm_enrich_requirements(text, provider)
                )
                enriched = future.result(timeout=60)
        else:
            enriched = asyncio.run(llm_enrich_requirements(text, provider))
        det_criteria = sum(len(r.acceptance_criteria) for r in result.requirements)
        llm_criteria = sum(len(r.acceptance_criteria) for r in enriched)
        if enriched and llm_criteria >= det_criteria:
            result.requirements = enriched
            result.llm_enriched = True
    except Exception as exc:  # noqa: BLE001 — enrichment is best-effort
        result.warnings.append(f"LLM requirement parse failed: {exc}")
    return result
