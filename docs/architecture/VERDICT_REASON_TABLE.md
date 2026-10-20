# 验收判定理由表 (verdict reason table)

由 `scripts/write_verdict_reason_table.py` 从 `evidence/verdict.py::REASON_TABLE` 生成；
`tests/unit/test_verdict_reason_table.py` 校验它与代码一致——
**这份文档不是第二份真源，是真源的投影**。

每一条理由都落在**两栏**的一栏：

- **阻断（确有问题）**：查出了问题，或记录**自相矛盾**。读者该去改代码/改记录。
- **缺口（证据不足）**：证据**取不到、归不了、判不了**。读者该去补证据。两者都 fail-closed，区别在**该谁行动**。

判定词由**在场的理由种类**推出：有阻断 → BLOCKED；只有缺口 → NEEDS_REVIEW；有 error → FAILED。

| 理由 key | 对外措辞 | 归属 |
|---|---|---|
| `zero_checks` | 零检查不能判定验收通过：请补充验收条件并接入适用检查器 | 缺口（证据不足） |
| `row_malformed` | 第 {index} 条检查记录格式无效 | 阻断（确有问题） |
| `row_without_contract_id` | {label}缺少契约标识 | 缺口（证据不足） |
| `duplicate_rows` | 契约 {cid} 存在重复检查行，需合并冲突证据 | 阻断（确有问题） |
| `contract_failed` | {label}检查失败 | 阻断（确有问题） |
| `row_unverifiable` | {label}：{text} | 缺口（证据不足） |
| `pass_without_evidence` | {label}标记通过但缺少证据引用 | 缺口（证据不足） |
| `pass_without_experiment` | {label}标记通过但缺少实验记录 | 缺口（证据不足） |
| `contract_set_broken` | 验收契约标识缺失或重复，无法确定完整覆盖范围 | 阻断（确有问题） |
| `missing_contract_result` | 缺少契约检查结果：{ids} | 缺口（证据不足） |
| `row_without_contract` | 检查记录没有对应验收契约：{ids} | 阻断（确有问题） |
| `no_valid_contract` | 没有有效的验收契约，无法确认需求覆盖 | 缺口（证据不足） |
| `summary_mismatch` | 检查汇总 {key} 与实际检查记录不一致 | 阻断（确有问题） |
| `contract_total_mismatch` | 契约总数与检查覆盖不一致 | 阻断（确有问题） |
| `findings_present` | 存在 {count} 项已确认问题，需要处理后重新验收 | 阻断（确有问题） |
| `pipeline_errors` | 执行过程有错误，无法形成有效验收结论 | 缺口（证据不足） |

共 16 条：阻断 8 条、缺口 8 条。

## 行的理由（矩阵行 → 对外措辞）

矩阵行可以带一个**受控代码**说明自己为什么没结论；判定层**拥有对外措辞**，节点的自由散文**不会被引用**（那是行级视图的事）。
判定层**算得出**的事实（契约是否获批、这一行是否跑过实验）**优先于**节点写的标签。

| 行代码 | 对外措辞 |
|---|---|
| `no_experiment` | 该契约没有任何实验产出结果; 禁止臆造 PASS/FAIL |
| `inconclusive` | 实验已运行但未得到可判定证据, 保持 UNVERIFIED |
| `contract_not_approved` | 契约未获批准: 需人工批准后方可作为验收依据 |

（这三句由 `evidence/verdict.py::_ROW_REASON_TEXT` 拥有；上表是它的投影。）
