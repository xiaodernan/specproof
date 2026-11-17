# Runbook Triage

**verdict: CONFIRMED** · alert `SpecproofApiDown` · generation_time_ms 45454

## Agents

| name | role | outcome | tokens |
|---|---|---|---|
| `investigate_explorer` | explorer | ok | 8010 |
| `investigate_tester` | tester | ok | 7414 |
| `investigate_security` | security | ok | 6456 |

## Findings

- **explorer** — `SpecproofApiDown` 表示 Prometheus 对 `job="api"` 的 `up` 值为 0，并持续至少 1 分钟；规则将其标为 `critical`。描述提到实例和值以及 §14 的可用性目标 99.5%，但规则本身不说明 API 为什么抓取失败，也不证明月度可用性已低于目标。

操作员首先应检查 Prometheus 所配置的 `api` 抓取目标及其抓取状态，确认具体 `instance` 和失败情况；其次检查 API 服务是否运行、是否能从 Prometheus 所在环境访问。事实包没有提供目标地址、抓取错误、服务日志或运行状态，因此不能进一步判断原因或给出特定故障指标。

仓库 README 支持 SpecProof 是用于 AI 辅助代码变更与独立验收的工具，项目依赖表显示其采用 Python/FastAPI 等技术；但给出的文档和证据文件清单没有包含 `runbook-triage.json` 等文件内容，也没有 API 健康检查、Prometheus 配置或本次告警现场证据。因此，规则本身支持上述告警含义，仓库材料不足以验证具体故障原因或完整的处置步骤。
- **tester** — 1. `SpecproofApiDown` fires when Prometheus reports `up{job="api"} == 0` continuously for 1 minute. It is labeled `critical`. The annotation describes the API scrape target as down and references the §14 monthly availability target of 99.5%. This indicates a failed scrape target; the rule alone does not establish why it is down or prove broader API unavailability.

2. The fact pack does not specify operator triage steps, so I cannot confirm the two first checks from it. It provides redacted API environment variables, but no service status, target instance, scrape errors, logs, or dependency health. Those details are missing, and naming checks such as dependencies or credentials as the first checks would be a guess.

3. The pack includes a `runbook-triage.json` evidence filename, but not its contents. The listed tests are about regression attribution, reused test-run sandbox errors, and acceptance severity parity; none establishes this alert’s interpretation or triage procedure. The commit summaries and redacted environment do not provide supporting evidence for those operational claims. Thus the alert rule supports the firing condition and stated annotation, but the repo docs/evidence support for triage and the §14 availability claim cannot be confirmed from this pack.
- **security** — 1. 含义：规则监测 Prometheus 中 `job="api"` 的抓取目标。`up{job="api"} == 0` 持续 1 分钟就触发严重级别的 `SpecproofApiDown`。摘要称 API 抓取目标 down；描述引用了 instance、value 和 §14 的 99.5% 月可用性目标。该规则本身不能证明 API 全面不可用，也不能证明月可用性已经低于目标。

2. 首先检查：
- Prometheus 中该 `job="api"` 目标的当前抓取状态及 `instance`，确认哪个目标被标为 down。
- API 服务及其抓取端点是否可达，并核对 Prometheus 的目标配置与抓取结果。

事实包没有提供目标详情、抓取错误、端点配置或服务状态，因此无法进一步判断根因，也无法指定应检查的具体端点或主机。

3. 仓库文档/证据是否支持这种解读：事实包给出了告警规则、最新证据文件名、最近提交摘要及脱敏后的 API 环境变量名称，但没有提供 runbook 或证据文件内容。因此规则语义可由告警本身支持；无法据此确认仓库文档或证据是否支持该告警的运维解读、具体检查步骤或根因。缺少相关文件内容和 Prometheus 目标/抓取数据。
