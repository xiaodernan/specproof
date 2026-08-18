# 完美体验指南 (EXPERIENCE GUIDE) — 从零到"卧槽"的 60 分钟

目标读者: 想亲手验证 SpecProof+SpecCraft 是否真的能打的人 (面试官/试用客户/自己)。
前提: 单机 Windows/Linux + Docker Desktop; 大模型接口 (OpenAI 兼容, 如
DeepSeek V4 Pro 网关); 无 GPU 要求。所有步骤按序执行, 每步给出预期输出。

## 第 0 步: 拿到代码并装好 (2 分钟)
git clone https://github.com/xiaodernan/specproof && cd specproof
pip install -e ".[dev]"            # Windows: python -m pip install -e ".[dev]"
cd apps/web && npm install && npm run build && cd ../..
docker compose -f compose.phase0.yml up -d --wait   # MySQL/Mongo/ES/Redis/RabbitMQ/MinIO
pwsh scripts/seed_sandbox_cache.ps1                  # 沙箱 Maven 缓存 (离线构建前提)

## 第 1 步: 11 维能力探测 — 网关到底行不行, 先测再说 (3 分钟)
$env:LLM_API_KEY="<你的key>"; $env:LLM_BASE_URL="https://llm-api.fagougou.com/v1"
$env:LLM_MODEL="deepseek-v4-pro"
python -m cli.specproof.main probe --base-url $env:LLM_BASE_URL --api-key $env:LLM_API_KEY --model deepseek-v4-pro
预期: 8/11 能力 (chat/streaming/json/tool_calls/thinking/reasoning/usage/error_codes 通过;
strict_tool_calls 400 → JSON Envelope 降级; thinking+工具不共存 → 思考分层)。
卖点: "我们不信任何网关的文档, 先探测再使用, 按能力自动降级。"

## 第 2 步: 旗舰拦截 — 一条命令看到真回归被抓住 (10 分钟)
python -m cli.specproof.main verify --repo demo/spring-backend --base base --head head-v1 --spec demo/requirement.txt
预期: BLOCKER (AUTH-01: @PreAuthorize 被移除) + MAJOR, 判定 BLOCKED;
产物: reports/verification-report-*.html (需求-证据矩阵) + capsules/capsule-*.zip + 拒绝通知。
python -m cli.specproof.main replay capsules/capsule-<AUTH-01>.zip
预期: 重放成功 — 同一反例在干净环境复现 (可重放证据)。

## 第 3 步: 评测 — 100 案例的硬数字 (5 分钟看结果, 后台数小时全量)
python -m cli.specproof.main eval --cases golden-cases --repo . --no-llm
预期 (全量完成后): Recall/Precision/F1 100/100/100, 0 误报 (docs/eval/eval-report.html)。
基线对比 (门槛 #14):
python -m cli.specproof.main baseline --cases golden-cases --repo . --mode llm
预期: 裸模型发现率 100% 但严格契约归因 0%、5 误报、1 次被注入影响;
SpecProof 100/100/100、0 误报、0 注入影响 → delta +100pp PASS。
卖点: "裸模型能看到问题, 但归因不了、会误报、会被注入操纵; 我们三者全零。"

## 第 4 步: SpecCraft — 让 V4 Pro 现场写代码并自我修复 (10 分钟)
cd D:\experim\speccraft-live-task02 (或 bench/tasks/task-02 的 fixture 目录)
python -m cli.specproof.main craft run task.spec --repo . --llm --budget-tokens 500000
预期: 模型自产 7 步计划 → 测试失败 → 模型诊断"整除判断写反" → apply_edit →
1 次迭代 DONE; 49s / 18017 tokens / KV 缓存命中 512; 3 测试全绿。
卖点: "写代码的 Agent 和验收的 Agent 是同一个平台的两半 — 开发完自动验收。"

## 第 5 步: Web 平台 — 看到整个企业版 (5 分钟)
$env:SPECPROOF_API_KEY="demo-key"; python -m uvicorn api.server:app --host 127.0.0.1 --port 8000
浏览器打开 http://127.0.0.1:8000 → 登录 (demo-key) →
Dashboard (任务/失败率/24h 时间线) → Job 详情 (SSE 实时阶段/Findings/证书/胶囊下载)
→ 契约中心 → 评测页 → 健康页 (6 依赖延迟)。
预期: 真实 MySQL 聚合、SSE 实时推送、签名证书可下载。

## 第 6 步: 可观测 (5 分钟)
docker compose -f compose.phase0.yml -f compose.observability.yml up -d
浏览器: Grafana http://localhost:3000 (admin/specproof_admin) → SpecProof SLO 看板 (15 面板);
Prometheus http://localhost:9090 → 7 条 SLO 告警规则已加载。

## 第 7 步: MCP — 任何外部 Agent 都能调用我们的验证 (3 分钟)
python -m cli.specproof.main mcp serve   # stdio 协议
在 Claude Code/Codex 里配置这个 MCP server → 它们获得
specproof_verify/contracts_list/eval_summary/craft_plan/health/replay_info 六个工具。
卖点: "我们不是另一个评审机器人, 而是给所有 AI Agent 提供中立验收的协议层。"

## 60 分钟体验完的结论语 (面试/演示收尾)
"这个项目回答了行业没人回答的问题: 代码是 AI 写的, 谁签字? — 用契约、
差分执行、变异测试和可重放证据, 把'验收'变成机器可验证的事实。"
