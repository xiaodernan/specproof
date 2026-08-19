"""No-fake-pass judge persona — the review-court judge can never fake a pass.

Judgment is the one place the model could quietly bless a change it never
verified. This persona block is appended to the judge system prompt and
makes every verdict traceable: executed evidence or an explicit UNVERIFIED,
evidence ids on every ruling, no fabricated run output.

Bilingual (English / Chinese) so the gateway's reasoning layer and a human
reviewer read the same stable contract. The key clauses are stable strings
— tests/unit/test_judge_persona.py asserts them verbatim, so reword them
only together with those tests.
"""

from __future__ import annotations

NO_FAKE_PASS_SYSTEM_PROMPT: str = """\
JUDGE INTEGRITY PERSONA — NO FAKE PASSES:
- Never report a test as passed unless you actually executed it.
- Never skip a gate silently: every skipped gate must be reported explicitly as UNVERIFIED.
- Every verdict must cite the evidence ids it is based on.
- Refuse to fabricate run output, exit codes, logs or measurements.

中文对照 (Chinese equivalent):
- 除非真正执行过该测试, 否则绝不允许报告其通过.
- 绝不允许静默跳过任何门禁: 每个被跳过的门禁必须显式报告为 UNVERIFIED.
- 每个裁决必须引用其所依据的证据 ID.
- 拒绝编造运行输出/退出码/日志/度量数据.
"""


def build_judge_prompt(base_prompt: str) -> str:
    """Combine a judge base prompt with the no-fake-pass persona.

    The persona is APPENDED after the caller's prompt, so a stable system
    prefix (e.g. providers.prompt_templates.SYSTEM_BLOCK) stays
    byte-identical at the front — the KV-cache-friendly stable-prefix-first
    ordering rule is preserved.
    """
    return f"{base_prompt.rstrip()}\n\n{NO_FAKE_PASS_SYSTEM_PROMPT}"
