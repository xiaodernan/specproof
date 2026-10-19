"""`contract.py` 的 `_spec_digest`（CLI 提案追踪用的 spec 文本哈希键）栅栏。

`_spec_digest` 把 spec 文本压成一个短键，用于把「propose 出来的候选」和「后来 approve 时
给出的 spec」对齐到同一条契约上。它跟 `agent/jobs.py` 的 `compute_spec_digest`（64 位全量
sha256）**不是一回事**——这里是 `sha256(text)[:16]`，截断到 16 位 hex。这个契约要钉死：
sha256 来源、截断长度、大小写、对同一输入稳定、对空串/空白有确定结果。回归一旦把它换成
别的哈希或改了截断长度，propose 与 approve 的 spec 对齐就会静默错配。
"""

from __future__ import annotations

import hashlib

from cli.specproof.commands.contract import _spec_digest


def _expected(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def test_is_sha256_truncated_to_16_hex() -> None:
    # 独立于实现地核对：必须是 sha256 的前 16 个 hex 字符
    assert _spec_digest("abc") == _expected("abc")
    assert len(_spec_digest("abc")) == 16
    assert _spec_digest("abc").islower() and all(
        c in "0123456789abcdef" for c in _spec_digest("abc")
    )


def test_known_vector() -> None:
    # sha256("abc") = ba7816bf8f01cfea414140de5dae2223... → 前 16 位
    assert _spec_digest("abc") == "ba7816bf8f01cfea"


def test_stable_for_same_input() -> None:
    assert _spec_digest("spec text") == _spec_digest("spec text")
    assert _spec_digest("spec text") == _expected("spec text")


def test_empty_string_and_whitespace_are_distinct() -> None:
    # 空串和白串都是合法 spec 文本，必须各得确定结果且互不相同
    assert _spec_digest("") == _expected("")
    assert _spec_digest(" ") == _expected(" ")
    assert _spec_digest("") != _spec_digest(" ")


def test_distinct_inputs_yield_distinct_digests() -> None:
    a = _spec_digest("requirement: login must rate-limit")
    b = _spec_digest("requirement: login must not rate-limit")
    assert a != b
    assert a == _expected("requirement: login must rate-limit")
    assert b == _expected("requirement: login must not rate-limit")
