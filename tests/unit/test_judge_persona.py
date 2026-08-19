"""Unit tests for the no-fake-pass judge persona (providers/judge_persona.py).

The persona's key clauses are STABLE STRINGS: these tests pin them
verbatim, so any reword must come with a coordinated update here.
"""

from providers.judge_persona import NO_FAKE_PASS_SYSTEM_PROMPT, build_judge_prompt
from providers.prompt_templates import SYSTEM_BLOCK


class TestNoFakePassPrompt:
    def test_never_pass_without_execution_clause(self) -> None:
        assert (
            "Never report a test as passed unless you actually executed it."
            in NO_FAKE_PASS_SYSTEM_PROMPT
        )
        assert "除非真正执行过该测试" in NO_FAKE_PASS_SYSTEM_PROMPT

    def test_no_silent_gate_skip_clause(self) -> None:
        assert "Never skip a gate silently" in NO_FAKE_PASS_SYSTEM_PROMPT
        assert "UNVERIFIED" in NO_FAKE_PASS_SYSTEM_PROMPT
        assert "绝不允许静默跳过任何门禁" in NO_FAKE_PASS_SYSTEM_PROMPT

    def test_verdict_must_cite_evidence_ids(self) -> None:
        assert (
            "Every verdict must cite the evidence ids it is based on."
            in NO_FAKE_PASS_SYSTEM_PROMPT
        )
        assert "证据 ID" in NO_FAKE_PASS_SYSTEM_PROMPT

    def test_refuse_to_fabricate_run_output(self) -> None:
        assert "Refuse to fabricate run output" in NO_FAKE_PASS_SYSTEM_PROMPT
        assert "拒绝编造运行输出" in NO_FAKE_PASS_SYSTEM_PROMPT

    def test_bilingual_blocks_both_present(self) -> None:
        assert "JUDGE INTEGRITY PERSONA — NO FAKE PASSES" in NO_FAKE_PASS_SYSTEM_PROMPT
        assert "中文对照" in NO_FAKE_PASS_SYSTEM_PROMPT


class TestBuildJudgePrompt:
    def test_combines_base_with_persona(self) -> None:
        combined = build_judge_prompt("BASE PROMPT")
        assert combined == "BASE PROMPT\n\n" + NO_FAKE_PASS_SYSTEM_PROMPT

    def test_appends_persona_without_mutating_base(self) -> None:
        # rstrip() normalizes only the trailing edge; the base content is
        # otherwise preserved verbatim (leading whitespace included).
        base = "  base with trailing space  "
        combined = build_judge_prompt(base)
        assert combined.startswith("  base with trailing space\n\n")
        assert NO_FAKE_PASS_SYSTEM_PROMPT in combined
        assert combined.endswith(NO_FAKE_PASS_SYSTEM_PROMPT)

    def test_keeps_system_block_prefix_byte_stable(self) -> None:
        # The persona must ride AFTER the stable system prefix so the
        # KV-cache-friendly ordering rule survives the combination.
        combined = build_judge_prompt(SYSTEM_BLOCK)
        assert combined.startswith(SYSTEM_BLOCK.rstrip() + "\n\n")
        assert combined.index(NO_FAKE_PASS_SYSTEM_PROMPT) > len(SYSTEM_BLOCK.rstrip())
