# SpecProof · 船员卡

> xiaodernan/specproof · 打印于 2026-11-15 18:30 UTC
> 本卡只刻本仓库 git-tracked 的事实；它不是签字、不是验收、不是承诺。

## 数字墙

| | |
|---|---|
| git 提交 | 2,509 |
| 账本节数 | 1,667 |
| 世界书卷（zh/en） | 84 / 84 |
| 源码行数 | 500,907 |
| Python 测试文件 | 611 |
| 前端测试文件 | 69 |
| 账本字节 (KB) | 3790.1 |
| 编年史最新节 | #1866 |

## 压测证据

| | |
|---|---|
| 证据件 | `2026-11-16-static-warm-3.json` |
| worst p99 | 1030.1 ms |
| 判定 | OK |
| Δ vs 上一件 | -507.2ms |

## 欠签（live 审计）

| | |
|---|---|
| 真·fleet 遥测 · OBSERVABILITY.md 签字 | awaiting-signature |
| 每周一敲门 · weekly-stress.yml | merged |
| 端口 8000 · 此刻谁在答 | port-free |

```
git log --oneline -1 && python scripts/build_repo_stats.py && python scripts/audit_unsigned.py
```

本卡每一个数字都能敲开：chronicle.json · repoStats.json · evidence.json · unsigned.json · engine.json（全部 git-tracked）。
LLM 账本：openai_compat · wkapi.pro · stream+include_usage 车道；cached_tokens：75,638（42.1% 前缀命中——不是 SLA）

> 本卡不含任何密钥、任何 API key、任何签名——本仓库从来不会把 `sk-…` 写进任何 git-tracked 文件。

