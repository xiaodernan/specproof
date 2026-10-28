"""Two user-facing surfaces must teach the same verdict vocabulary as the code.

`evidence/verdict.py::VERDICT_VOCABULARY` is `{VERIFIED, BLOCKED, NEEDS_REVIEW,
FAILED}` — four words, and `UNVERIFIED` is **not** one of them: it is the result
of a single requirement's matrix row ("this requirement has no evidence yet").

README's "如何读结果" section listed `VERIFIED / BLOCKED / FAILED / UNVERIFIED`:
it presented a row-level result as a verdict, and it **omitted NEEDS_REVIEW** —
a real verdict with its own exit code (3). A reader whose run ended in
NEEDS_REVIEW had nothing in the README to look up, and a reader who saw
UNVERIFIED could reasonably conclude the whole change was unverified.

The fix keeps UNVERIFIED in the text (it matters) but labels it as a row-level
result, and lists the four verdict words as the verdict words. These legs keep
the two surfaces — README and the CLI's own help epilog — tied to the code.
"""

from __future__ import annotations

import re
from pathlib import Path

from cli.specproof.main import HELP_EPILOG
from evidence.verdict import VERDICT_VOCABULARY

_README = Path(__file__).resolve().parents[2] / "README.md"
_SECTION = "## 如何读结果"
_BULLET_WORD = re.compile(r"^- `([A-Z_]+)`", re.M)


def _readme_verdict_section() -> str:
    text = _README.read_text(encoding="utf-8")
    start = text.find(_SECTION)
    assert start >= 0, f"README has no {_SECTION!r} section"
    end = text.find("\n## ", start + len(_SECTION))
    return text[start:end if end > 0 else len(text)]


def test_readme_lists_exactly_the_verdict_vocabulary() -> None:
    section = _readme_verdict_section()
    listed = set(_BULLET_WORD.findall(section))

    assert listed == set(VERDICT_VOCABULARY), (
        "README's result list and evidence/verdict.py disagree. "
        f"missing from README: {sorted(set(VERDICT_VOCABULARY) - listed)}; "
        f"listed but not a verdict: {sorted(listed - set(VERDICT_VOCABULARY))}"
    )


def test_unverified_is_taught_as_a_row_result_not_a_verdict() -> None:
    section = _readme_verdict_section()

    assert "UNVERIFIED" in section, (
        "UNVERIFIED is still something a reader will see on a row; removing it "
        "from the section would leave that word unexplained"
    )
    assert "UNVERIFIED" not in set(_BULLET_WORD.findall(section)), (
        "UNVERIFIED is a matrix row result, not a verdict word — it must not be "
        "presented as one"
    )
    assert "行级" in section, (
        "the section must say UNVERIFIED is a per-requirement (row-level) result"
    )


def test_the_cli_help_teaches_the_same_four_words() -> None:
    missing = [word for word in VERDICT_VOCABULARY if word not in HELP_EPILOG]

    assert not missing, (
        f"the CLI's help epilog never mentions {missing}; a user who reads "
        "`specproof --help` would not learn these verdicts exist"
    )


def test_the_readme_states_the_real_exit_code_of_every_verdict() -> None:
    """Each bullet must carry *its own* code, not just the word "退出码"."""
    from cli.specproof.commands.verify import VERDICT_EXIT_CODES

    assert set(VERDICT_EXIT_CODES) == set(VERDICT_VOCABULARY), (
        "the exit-code table and the verdict vocabulary must cover the same words: "
        f"codes={sorted(VERDICT_EXIT_CODES)} vocabulary={sorted(VERDICT_VOCABULARY)}"
    )

    section = _readme_verdict_section()
    wrong: list[str] = []
    for word, code in sorted(VERDICT_EXIT_CODES.items()):
        bullet = next(
            (ln for ln in section.splitlines() if _BULLET_WORD.match(ln) and word in ln),
            None,
        )
        if bullet is None:
            wrong.append(f"{word}: no bullet")
        elif f"退出码 {code}" not in bullet:
            wrong.append(f"{word}: bullet does not say 退出码 {code}")

    assert not wrong, (
        "README's per-verdict exit codes disagree with "
        f"VERDICT_EXIT_CODES ({VERDICT_EXIT_CODES}): {wrong}. A reader who scripts "
        "against the README would branch on the wrong number"
    )
