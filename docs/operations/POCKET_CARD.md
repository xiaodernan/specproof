# SpecProof 口袋卡 · 30 秒上手

> 打印这一页（A4，单面即可）。随手查随手用。更细的说明见 `docs/operations/USER_GUIDE.md`；跑起来再说
> —— 这一页只讲「出门前必须带着的常识」。

---

## 出门前带着这 5 件事

1. **这是验收，不是写代码。** 你交 base、head、spec；SpecProof 交回铁证——不是情绪，不是形容词。
2. **先看红的地方，再看绿的地方。** BLOCKER（阻断）不许「考虑过就放行」；UNVERIFIED（证据不足）不是 PASS。
3. **缓存命中率是观测值，不是契约。** wkapi.pro 的 cached_tokens 可能报 `null`，那就老老实实显示「—」，绝不补零（#1723）。
4. **worktree 是你自己的。** 演示仓：demo/spring-backend（`base` = 原始实现，`head-v1` = 故意删了 `@PreAuthorize`）。`base..head-v1` 差 1 行——这 1 行就是案例。
5. **自己动手 30 秒自检**：`python scripts/demo_doctor.py` 六项检查——全绿再跑验收，有 WARN 先看清楚再决定。

## 三个不要

1. **不要相信口头“考虑过了”。** 红灯就是红灯；考虑不是一种状态。
2. **不要相信 96.5% 的命中率。** 那是网关自己 system prompt 的常数；你的 prompt 没有命中可言（#1723）。
3. **不要相信没声音就等于没问题。** 检查器崩溃 = 对应验收条件 UNVERIFIED，不是 PASS。

## 五个只能照做的命令（都真实存在于本仓库）

```bash
python scripts/demo_doctor.py                      # 自检（零 Docker，零网络）
python scripts/build_chronicle.py                  # 重建 apps/web/src/pages/chronicle.json（账本 → JSON）
python -m pytest tests/unit/test_ledger_section_ids_are_unique.py \
  tests/unit/test_ledger_section_numbers_are_unique.py \
  tests/unit/test_ledger_evidence_claims_are_true.py \
  tests/unit/test_ledger_queue_pointers_resolve.py   # 账本四件套
python scripts/provider_smoke.py                   # 真实 LLM 端到端 smoke（wkapi.pro / gpt-6-sol）
python scripts/sync_portfolio.py                   # 重建 portfolio 展柜数据（仅重建，不推送）
```

## 报告里常见的五个词

| 词 | 中文意思 | 你该做什么 |
|---|---|---|
| **base_pass_head_fail** | 变更引入的回归 | 必须看，必须修，证据在 capsule 里 |
| **UNVERIFIED** | 证据不足，不通过也不失败 | 别当通过合并；补证据再验 |
| **BLOCKER** | 阻断合并 | 修完或拿出新证据，否则不能过 |
| **capsule** | 可复现证据包 | 出了问题，这就是你复盘的证据 |
| **NEEDS_REVIEW** | 证据了结不了 | 找一个人读给那一条看 |

## 出事的时候

- `python scripts/demo_doctor.py` 告诉你 demo 仓标签/差异/需求文档是不是完整；
- `npm --prefix apps/web run build`（或 tsc --noEmit）看代码能不能构建；
- 全量 Python 单元测试 **不会**在本机内存受限时跑完——相信具体 gate，不要相信「全绿」；
- 账本里每一笔都附了命令和输出，文档说“可能”的地方，账本只会让你看到实测。

**证据先于人。**
