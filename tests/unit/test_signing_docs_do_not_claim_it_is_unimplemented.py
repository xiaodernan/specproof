"""签名能力的台账声称必须与代码事实双向一致 — #230.

`evidence/signing.py` 自 P5 起就是真的 Ed25519: 发出 in-toto 风格语句、
`verify_statement` 能验回同一把密钥、密钥从环境读且读不到就抛
`SigningError`。`craft/accept.py` 和 `specproof verify` 都接了线, 接线的方式
是 fail-closed —— 没有密钥就 ERROR, 绝不静默交出一份没签过名的产物。
`tests/unit/test_signing.py` 有 5 条往返测试, `test_craft_accept.py:418`
用真的公钥验过真的签名。

但两份台账仍在说反话:

* ``CLAUDE.md`` 的「Phase 0 已知限制」: 「Merge Certificate 使用 SHA-256
  哈希，Ed25519 签名计划 Phase 1+」;
* ``PRODUCT_ROADMAP.md`` 4.3 (未勾选): 「Ed25519（现为 SHA-256 哈希占位）」。

CLAUDE.md 是读者拿到的第一份文件 —— 照它办事的人会以为证书没有签名能力,
于是要么重造一遍、要么干脆不去验签。两处都不是笔误而是过期: 4.3 勾选框
从来没人回来改过, 而 P5 早在 ADR-011 就被接受了。

两个方向都钉, 与 ``test_drills_gap_claims_hold.py`` 同规矩:

* 代码侧真的签名能力消失 (函数没了 / accept 不再接线 / 往返验签失败) → 红,
  迫使台账把「已落地」改回「计划」, 谁都不能单方面宣布完成;
* 台账把「已落地」改回「计划/占位」 → 同样红。

反向断言查的是**假句本身** (下表的精确措辞), 不查「占位」二字的任意出现:
新句子里的「而非占位签名」正是在否认那句假话, 不能让它把门判红。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from evidence.signing import (
    generate_key_hex,
    public_key_hex,
    sign_json_document,
    verify_statement,
)

REPO = Path(__file__).resolve().parents[2]
CLAUDE_MD = REPO / "CLAUDE.md"
ROADMAP = REPO / "docs" / "operations" / "PRODUCT_ROADMAP.md"

#: Verbatim claims these two files printed as fact while the feature already
#: existed. Matching an *unlabelled* occurrence of any of them is a failure —
#: a revert to one of these exact wordings is how the stale state came back.
STALE_SIGNING_CLAIMS = (
    "Ed25519 签名计划 Phase 1+",
    "现为 SHA-256 哈希占位",
    "Ed25519（现为 SHA-256",
)

#: FIX-14: a false sentence may stay quoted — the record of *finding* it is
#: evidence, and deleting it deletes that record. What is forbidden is quoting
#: it without saying on the same line that it is false, because then a reader
#: (or a grep) takes it at face value. Without this rule the fix for a stale
#: claim cannot be written down: §36 quotes both claims verbatim.
CORRECTION_MARKERS = ("假句", "更正", "已过期", "原句", "历史")


def _unlabelled_claims(text: str) -> list[str]:
    """Stale claims that appear without saying they are stale."""
    out: list[str] = []
    for line in text.splitlines():
        for claim in STALE_SIGNING_CLAIMS:
            if claim in line and not any(m in line for m in CORRECTION_MARKERS):
                out.append(claim)
    return out


def _claude() -> str:
    return CLAUDE_MD.read_text(encoding="utf-8")


def _roadmap() -> str:
    return ROADMAP.read_text(encoding="utf-8")


def test_the_documented_capability_really_round_trips() -> None:
    """The anchor: docs are only allowed to say 已落地 if this is true.

    If signing ever stops working, this reds first and the two doc tests
    below fail alongside it — one run tells the whole story instead of a
    doc test reding with no explanation.
    """
    previous = os.environ.get("SPECPROOF_SIGNING_KEY")
    os.environ["SPECPROOF_SIGNING_KEY"] = generate_key_hex()
    try:
        payload = {"job": "j1", "verdict": "VERIFIED"}
        statement = sign_json_document(payload)
        assert statement["payload"] == payload
        assert len(statement["signatures"]) == 1
        assert verify_statement(statement, public_key_hex()) is True
    finally:
        # Restored, not just unset: the signing suite generates its own key at
        # import time and other lanes may be mid-run.
        if previous is None:
            os.environ.pop("SPECPROOF_SIGNING_KEY", None)
        else:
            os.environ["SPECPROOF_SIGNING_KEY"] = previous


def test_the_accept_path_is_wired_to_signing() -> None:
    """A certificate the pipeline cannot sign is the stale claim made real."""
    accept = (REPO / "craft" / "accept.py").read_text(encoding="utf-8")
    assert re.search(r"from evidence\.signing import .*sign_json_document", accept), (
        "craft/accept.py no longer imports the signer — the roadmap's 已落地 "
        "claim is now false and must be reverted in the same commit"
    )
    # fail-closed is what makes the claim "无密钥即 ERROR" checkable at all.
    assert "signing_unavailable" in accept, (
        "the fail-closed branch is gone; an unsigned accept could slip through"
    )


def test_claude_md_does_not_describe_the_certificate_as_unsigned() -> None:
    """CLAUDE.md is the first file a reader gets — its claim is the default."""
    text = _claude()
    unlabelled = _unlabelled_claims(text)
    assert not unlabelled, (
        f"CLAUDE.md asserts {unlabelled!r} without saying on that line that it "
        f"is false, while evidence/signing.py implements Ed25519 and "
        f"craft/accept.py wires it in fail-closed (#230). Revert the doc or "
        f"revert the code — not one alone. (Quoting the old sentence is "
        f"allowed, but only labelled 假句/更正 on the same line.)"
    )
    assert "Ed25519" in text, (
        "CLAUDE.md no longer mentions Ed25519 at all; the limitation it "
        "replaced has vanished rather than been corrected"
    )


def test_the_roadmap_does_not_call_ed25519_a_placeholder() -> None:
    """The 4.3 checkbox was never revisited after P5 landed (#230)."""
    text = _roadmap()
    unlabelled = _unlabelled_claims(text)
    assert not unlabelled, (
        f"PRODUCT_ROADMAP.md asserts {unlabelled!r} unlabelled — P5 shipped "
        f"Ed25519 signing (ADR-011 accepted), so the row describes a state "
        f"that no longer exists (#230). Label it 假句 if it is there as "
        f"evidence of this fix."
    )
    row = next(
        (ln for ln in text.splitlines() if "**4.3" in ln), ""
    )
    assert row.startswith("- [x]"), (
        f"4.3 is still open while Ed25519 is implemented; a reader counting "
        f"unchecked boxes will believe signing is missing: {row!r}"
    )
    assert "KMS/HSM" in row, (
        f"4.3 was checked off without naming what genuinely remains — the "
        f"honest version names the gap it does not close: {row!r}"
    )


def test_a_labelled_false_sentence_may_remain() -> None:
    """The rule's other half — or the fix could not be written down.

    §36 quotes both stale claims verbatim, because the record of *finding*
    them is the only evidence the review happened. This asserts labelling
    makes a quote legal and *not* labelling does not, so neither half of the
    rule can drift on its own.
    """
    claim = "Ed25519 签名计划 Phase 1+"
    assert _unlabelled_claims(f"- {claim}") == [claim], (
        "an unlabelled quote must still be caught"
    )
    for marker in CORRECTION_MARKERS:
        assert _unlabelled_claims(f"- {marker}：「{claim}」") == [], (
            f"{marker!r} must legalise a labelled quote"
        )

