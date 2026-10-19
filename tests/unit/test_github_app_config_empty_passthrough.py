"""`integrations/github_checks.GitHubAppConfig.from_env` 的「密钥空透传诚实性」栅栏。

`GITHUB_APP_PRIVATE_KEY_FILE` 是 #260 关心的一个 env 旋钮：它在 `.env.example` 里常被写成
`${X:-}` 的空透传形态（声明了但值为空）。这个旋钮必须被**诚实**地读：

- 四个相关变量全空 → 返回 `None`（调用方跳过 GitHub 发布），绝不能因「变量声明了但空」就崩；
- ID 已配、但 `GITHUB_APP_PRIVATE_KEY_FILE` 是空串 → 必须 `GitHubAppConfigError`（partial config
  要响，不能把空串当有效密钥静默放过）；
- `GITHUB_APP_PRIVATE_KEY_FILE` 指向不存在的文件 → 必须 `GitHubAppConfigError`（被 `OSError`
  兜底成清晰错误，而不是抛出未处理的 `FileNotFoundError` 堆栈）；
- 行内 `GITHUB_APP_PRIVATE_KEY` 与 `GITHUB_APP_PRIVATE_KEY_FILE` 都能真正落到 `private_key_pem`
  （证明这个旋钮确实到达了读它的进程，不是声明了却没人用）。

这些断言不依赖网络、不依赖真实 RSA 密钥，纯测「空/缺/坏」三类输入的诚实处理。
"""

from __future__ import annotations

import pytest

from integrations.github_checks import GitHubAppConfig, GitHubAppConfigError

_VARS = (
    "GITHUB_APP_ID",
    "GITHUB_APP_INSTALLATION_ID",
    "GITHUB_APP_PRIVATE_KEY",
    "GITHUB_APP_PRIVATE_KEY_FILE",
)


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _VARS:
        monkeypatch.delenv(name, raising=False)


def test_all_empty_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # 空透传（四个变量都声明但为空）必须干净跳过，而不是崩
    _clear(monkeypatch)
    assert GitHubAppConfig.from_env() is None


def test_ids_present_but_key_file_empty_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ID 配了、私钥旋钮是空串：partial config 要响，不能被当有效密钥放过
    _clear(monkeypatch)
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_FILE", "")
    with pytest.raises(GitHubAppConfigError):
        GitHubAppConfig.from_env()


def test_key_file_missing_path_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # 文件旋钮指向不存在的路径：必须被 OSError 兜底成清晰错误，而非裸 FileNotFoundError
    _clear(monkeypatch)
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_FILE", "/no/such/key.pem")
    with pytest.raises(GitHubAppConfigError):
        GitHubAppConfig.from_env()


def test_inline_key_reaches_pem(monkeypatch: pytest.MonkeyPatch) -> None:
    # 行内密钥旋钮必须真正到达 private_key_pem
    _clear(monkeypatch)
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "INLINE-PEM")
    cfg = GitHubAppConfig.from_env()
    assert isinstance(cfg, GitHubAppConfig)
    assert cfg.private_key_pem == "INLINE-PEM"


def test_key_file_content_reaches_pem(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # 文件旋钮必须真正把文件内容读进 private_key_pem（旋钮到达读它的进程）
    _clear(monkeypatch)
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "456")
    key_file = tmp_path / "app.pem"
    key_file.write_text("FILE-PEM-CONTENT", encoding="utf-8")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_FILE", str(key_file))
    cfg = GitHubAppConfig.from_env()
    assert isinstance(cfg, GitHubAppConfig)
    assert cfg.private_key_pem == "FILE-PEM-CONTENT"
