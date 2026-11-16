# SpecProof · 船员卡

> xiaodernan/specproof · 打印于 2026-11-16 09:27 UTC
> 本卡只刻本仓库 git-tracked 的事实；它不是签字、不是验收、不是承诺。

## 数字墙

| | |
|---|---|
| git 提交 | 2,557 |
| 账本节数 | 1,698 |
| 世界书卷（zh/en） | 114 / 114 |
| 源码行数 | 508,008 |
| Python 测试文件 | 618 |
| 前端测试文件 | 73 |
| 账本字节 (KB) | 3852.3 |
| 编年史最新节 | #1897 |

## 压测证据

| | |
|---|---|
| 证据件 | `2026-11-16-static-warm-6.json` |
| worst p99 | 1058.3 ms |
| 判定 | OK |
| Δ vs 上一件 | +23.3ms |

## 欠签（live 审计）

| | |
|---|---|
| 真·fleet 遥测 · OBSERVABILITY.md 签字 | signature-block-found |
| 每周一敲门 · weekly-stress.yml | merged |
| 端口 8000 · 此刻谁在答 | other-project-answering |

```
git log --oneline -1 && python scripts/build_repo_stats.py && python scripts/audit_unsigned.py
```

本卡每一个数字都能敲开：chronicle.json · repoStats.json · evidence.json · unsigned.json · engine.json（全部 git-tracked）。
LLM 账本：openai_compat · wkapi.pro · stream+include_usage 车道；cached_tokens：75,638（42.1% 前缀命中——不是 SLA）

> 本卡不含任何密钥、任何 API key、任何签名——本仓库从来不会把 `sk-…` 写进任何 git-tracked 文件。

