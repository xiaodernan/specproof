"""`_resolve_capsule` 的元数据存分支三态（#281 只盖了 legacy 回退）。

`_resolve_capsule` 的契约：
- 存可用时，先问元数据存；
- 命中且 `path_hint` 指向的文件**存在** → 返回 `(capsule_path, record)`（成功）；
- 命中但 `path_hint` 指向的文件**已失效** → 诚实报错 `SystemExit(1)`；
  存知道有这个胶囊，但载荷搬走了；
- 存里**没有**记录、且入参**像对象引用** → 诚实报错 `SystemExit(1)`（不像路径、存里又查不到）；
- 存里没有记录、且入参是**一条存在的普通路径** → 不报错，落到 legacy 分支返回 `(path, None)`。

后两态的边界最容易被回归静默翻转（把「存 miss + 像引用」误处理成「当路径找」会吞掉错误）。
本测试用桩 `storage.object_metadata.resolve_object` + 非 None 的存，把三态确定化，无需 MySQL。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import storage.object_metadata as object_metadata
from cli.specproof.commands import replay
from cli.specproof.commands.replay import _looks_like_object_reference, _resolve_capsule


class _Record:
    """Minimal stand-in for an object metadata record (only `path_hint` used)."""

    def __init__(self, path_hint: str) -> None:
        self.path_hint = path_hint


@pytest.fixture
def open_store(monkeypatch: pytest.MonkeyPatch):
    """Force the metadata store to be "available" so the store branch runs."""
    sentinel = object()
    monkeypatch.setattr(replay, "_open_store", lambda: sentinel)
    return sentinel


def test_store_hit_with_existing_path_returns_record(
    open_store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = tmp_path / "capsule.zip"
    existing.write_text("payload")
    monkeypatch.setattr(
        object_metadata,
        "resolve_object",
        lambda store, reference: _Record(str(existing)),
    )
    path, record = _resolve_capsule("some-ref")
    assert str(path) == str(existing)
    assert record is not None
    assert record.path_hint == str(existing)


def test_store_hit_with_missing_path_exits_1(
    open_store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "gone.zip"
    monkeypatch.setattr(
        object_metadata,
        "resolve_object",
        lambda store, reference: _Record(str(missing)),
    )
    with pytest.raises(SystemExit) as exc:
        _resolve_capsule("some-ref")
    assert exc.value.code == 1


def test_store_miss_that_looks_like_reference_exits_1(
    open_store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        object_metadata, "resolve_object", lambda store, reference: None
    )
    ref = "12345678123456781234567812345678"  # 32-hex object id (no dashes)
    assert _looks_like_object_reference(ref) is True
    with pytest.raises(SystemExit) as exc:
        _resolve_capsule(ref)
    assert exc.value.code == 1


def test_store_miss_with_plain_existing_path_falls_through_to_legacy(
    open_store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        object_metadata, "resolve_object", lambda store, reference: None
    )
    existing = tmp_path / "legacy.zip"
    existing.write_text("payload")
    # a real existing path must not be mistaken for a missing ref
    path, record = _resolve_capsule(str(existing))
    assert str(path) == str(existing)
    assert record is None
