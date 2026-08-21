# SWE-bench 与 Agent 生态实时情报 (代理抓取, 2026-08-19)

来源: 通过本地代理直接抓取 swebench.com 与 GitHub API (web_search 工具故障期间的真实联网路径),
数字为抓取当刻的真实数据。

## SWE-bench Verified 当前格局 (swebench.com 实时)

- mini-SWE-agent: 65% on SWE-bench Verified, 100 行 Python (站点头条, 运行日期 2026-02-17) —
  当前默认视图 (Verified) 下所有模型在同一 mini-SWE-agent 环境比较分数;
- SWE-agent 1.0: 开源 SOTA on SWE-bench Lite (站点头条);
- 历史参照: 经典 SWE-agent 12.47% on SWE-bench (老版本基线);
- 站点内嵌全量 leaderboard JSON (agent/cost/date/results) — 后续可脚本化提取精确榜单。

## GitHub 热门 Agent 框架 (API 搜索, 实时 star)

| 项目 | stars | 定位 |
|---|---|---|
| langchain-ai/langchain | 144,510 | agent 工程平台 |
| TauricResearch/TradingAgents | 98,852 | 多智能体金融交易 |
| FoundationAgents/MetaGPT | 69,887 | 多智能体软件公司 |
| microsoft/autogen | 60,504 | agentic AI 编程框架 |
| crewAIInc/crewAI | 57,290 | 角色扮演式自主 agent 编排 |

## 对本项目的启示 (面试对标口径)

1. 评测叙事已统一到 SWE-bench Verified + 同环境比较 (mini-SWE-agent 环境) —
   我们的 SWE-bench-Lite harness (W45 车道) 应同时准备 Verified 口径, 声明同 harness 环境比较;
2. 65% (mini 环境) vs 12.47% (旧版) 的巨大差距说明 harness/环境标准化比模型本身更关键 —
   这正是 SpecProof 的立场: 验收必须在受控、可复现环境 (Base/Head 差分 + 沙箱) 里做;
3. 开源 SOTA (SWE-agent 1.0) 是我们在 SWE-bench Lite 上的对标物;
4. GitHub 头部 agent 框架全部主打多智能体编排 — 我们的 ParallelRunner (只读并行+写集
   fail-closed) 可按同样语言讲, 且多了安全约束差异点。

## 后续动作

- W45 落地后: 脚本提取 swebench.com 内嵌 JSON 生成精确榜单表;
- 面试材料 §3 对标表更新为上述真实数字 (替换占位)。
