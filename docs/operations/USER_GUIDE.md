# SpecProof 使用手册 · User Guide

> **English edition**: [EN/USER_GUIDE_EN.md](./EN/USER_GUIDE_EN.md) · 本文是中文原版；两种语言互为镜像。
> 目标读者：**刚克隆仓库的人 / 要给面试官展示的人 / 希望看完全部产品面的人**。
> 阅读顺序：§1 快速"打就完事儿"、§2 完整体验路径、§3 完整模块目录、§4 中英文切换。

---

## §1 · 5 分钟快速路径

### 1.1 进门（无凭据）

```bash
git clone https://github.com/xiaodernan/specproof && cd specproof
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"    # Windows
cd apps/web && npm install && npm run build && cd ../..
pwsh scripts/start_local_light.ps1                              # 零 Docker 模式也能跑
# 或完整 Docker 模式：
docker compose -f compose.phase0.yml up -d --wait
```

### 1.2 看一眼所有面（5 分钟）

直接打开 `http://127.0.0.1:5173/`——侧栏已有 18 个一级入口：

| 组 | 入口 | 你能马上做的事 | 铁证 |
|---|---|---|---|
| 工作空间 | 工作台 | 看当天所有验收轨迹 + 未解决的 BLOCKER | — |
| 工作空间 | 变更验收 | 进入 Jobs 列表；点任意一条进详情 | — |
| 工作空间 | AI 开发 | 进入 SpecCraft——让 AI 写代码并自我修复 | LLM 调用 + 自我纠错 |
| 质量与证据 | 需求覆盖 | 看 requirement → contract_id → 判决矩阵 | 真证据 |
| 质量与证据 | 验证规则 | 看每一条契约的 checker_type（http/sql/…） | — |
| 质量与证据 | 效果评测 | 看评测分数（F1/召回/Precision）的真实数字 | 100 例 golden |
| 管理 | 用量与账单 | 看 LLM token 用量 + 缓存命中率 | 直连 wkapi.pro |
| 管理 | 审计轨迹 | 看每一步 audit_logs 写入链路 | 合规 |
| 管理 | 模型连接 | 切换 OpenAI 兼容网关的真实 key | — |
| 管理 | 服务状态 | 健康 (mysql/redis/rabbitmq/minio) + 延迟分布 | — |
| —— | 史诗 | 六卷竹简式 SpecProof 创世记 | 全部锚定真实提交 |
| —— | 巡览 | 新用户交互预演（六桩） | 你按了才算数 |

> 没有 .env 也能看 —— 验收不需要 .env 才能视察；需要 `.local/llm.json` 才能跑真实 LLM。

### 1.3 跑一遍真实验收（10 分钟）

```bash
# 自带 demo：基准 base vs 现有的 head-v1——后者是本仓库故意注入了「移除 @PreAuthorize」
specproof verify \
  --repo demo/spring-backend \
  --base base --head head-v1 \
  --spec demo/requirement.txt \
  --depth FAST --no-llm
```

预期输出：

```
Contracts compiled: 6
  [!] AUTH-01 (http) -> FAIL      ← 差分抓到 @PreAuthorize 被移除
  [+] UNIQUE-01 (sql) -> PASS
  [?] TOKEN_INVALIDATION-01 (redis) -> UNVERIFIED
  [+] BACKWARD_COMPATIBLE-01 (openapi) -> PASS
  [+] EVENT_ONCE-01 (rabbitmq) -> PASS
  [+] TRANSACTION-01 (sql) -> PASS
VERDICT: BLOCKED
```

那个 `AUTH-01 FAIL` 就是本仓库要教你的、**一个真实的证据**。
不要相信 AI 帮你看代码；相信**差分**。

---

## §2 · 完整体验路径（20 分钟朝向门）

### 2.1 打开 /ui-kit — 全 Aurora 组件库对照表

侧栏 → `/ui-kit`（不需要凭据）。这里罗列出：Button、Breadcrumbs、Table、StatCard、StatusPill、Progress、Skeleton、Modal、Empty/Degraded 等全部组件的阴影、圆角、色阶、动效——
这是给「把 SpecProof 复刻回自己的设计系统」的人准备的。

> 教科书：本仓库 apps/web/src/ui/ 下每个组件 `.tsx` 均有 stories；/ui-kit 是它们的聚合展示。

### 2.2 打开 `#/usage` — LLM 缓存账

切换侧栏 `缓存健康` —— wkapi.pro 实测命中 ~84%（2270 字符稳定 prefix）。
> `hit_rate` 的分母是 `hit_basis_calls`（网关上报了缓存的调用数），不是 `calls` —— 保证诚实。

### 2.3 打开 `#/tour` —— 新手走廊

**六桩真实动作**：每桩都按一下，seal 盖一下；六盖凑齐 → 进度条满 → 出现一句话。
> 全在你 localStorage；谁都代替不了你点。

### 2.4 打开 `#/explorer` — 案卷铁页

点击近期一桩验收 → 看到红印「验讫」，仓库 / 变更 / 开卷日期 / 案卷号，四行 StatCard + AUTH-02 一桩发现 —— **没有一句凭空叙事**。

### 2.5 打开 `#/epic` — 史诗

六卷竹简 —— 每卷锚死 git 真实提交：卷一（铁证的铸造史）、卷五（史官守夜：#1645、#1668、#1672 真实账本）。**中文版 22.3KB**。
英文版同构见 `docs/world/EN/SPECROOF_WORLD_EN.md`。

### 2.6 打开 `#/mcp` —— 给 AI Agent 当现场法官

```bash
specproof mcp tools          # 列出 7 个工具
specproof mcp serve          # 启动 stdio MCP server
```
把这个 server 配进 Claude Code / Codex，它们就能把 "我帮你检查这段代码" 变成 `specproof_verify` 调用，而不是信口说。

### 2.7 跑一遍真实 LLM（需要 .local/llm.json）

`.local/llm.json.example` 已在仓库。填入：

```json
{
  "base_url": "https://wkapi.pro/v1",
  "api_key": "sk-…你的key",
  "model": "gpt-6-sol",
  "protocol": "chat_completions"
}
```

```bash
# 探针 + 首次真实跑：
specproof probe --base-url https://wkapi.pro/v1 --model gpt-6-sol --api-key sk-…
specproof verify --repo demo/spring-backend --base base --head head-v1 --spec demo/requirement.txt --depth FULL
```

> 预期：**与 FAST 模式同样的 BLOCKED**，但这次判决由 GPT 6 sol 亲自下，且 `token 计入 .local/llm_usage.jsonl`。
> 若 wkapi.pro 路由失稳：`hit_rate` 可能在 `75%-84%` 之间振荡；`cached_tokens` 不为 null 即可。

---

## §3 · 模块目录（49 页应用）

| 路由 | 模块 | 一句话 |
|---|---|---|
| `/dashboard` | 工作台 | 任务、失败、24h 时间线、blocked 投递盘 |
| `/jobs` + `/jobs/:id` | 变更验收 | 流程化 5 步 RED/GREEN 证据 + capsule |
| `/jobs/new` | 新建验证 | 填 repo/base/head/spec，FAST\|FULL 双深度 |
| `/matrix` | 需求覆盖 | contract_id × evidence_type 表 |
| `/contracts` | 验收规则 | 列出所有契约 + 不知道也能读的解释 |
| `/eval` | 效果评测 | F1/P/R 分类诊断 + golden 对照 |
| `/billing` | 用量与账单 | 真 wkapi.pro 实测 token + hit_rate |
| `/audit` | 审计轨迹 | 每一步 audit_logs 写入，不丢任何 |
| `/health` | 服务状态 | 6 依赖延迟分布 + 60 面板 SLO 告警触发 |
| `/settings` | 模型连接 | 切换 OpenAI 兼容网关（DeepSeek / wkapi / 任意 / Azure / OpenAI） |
| `/mcp` | MCP 适配 | 给外部 AI agent 用的工具目录 + stdio |
| `/admin/identity` | 租户与权限 | RBAC、访问控制、审计 |
| `/ui-kit` | 设计系统 | 全 Aurora 组件对照 |
| `/epic` | 史诗 | 中文创世记，每卷锚死 git 哈希 |
| `/tour` | 巡览 | 新手交互式走廊，六盖一齐验讫 |
| `/explorer` | 案件档案 | 铁证装订 - 红印验讫封面 |
| `/lexicon` | 铁证词典 | 十四个词，每词可搜、可点开、锚到仓库真实位置 |
| `/gestures` | 验收官十四式 | 十四种验收站姿一网打尽——可敲盖、见铁印 |
| `/museum` | 铁证博物馆 | 十二件实证展品，每件锚到账本真实条目 |
| `/usage` | 缓存健康 | 真 hit_rate + 计费链条 |
| `/guide` | 上手指南 | 从 clone 到第一个 BLOCKED 的 4 步 |
| `/readme` | 推荐读物 | 本仓库的阅读者地图 |

---

## §4 · 中英文切换（if the screen shows mixed colours of text）

顶栏**语言切换钮**（显示 `EN` / `中`）随时可切；选择存本机 `specproof_locale`，刷新后保留；
文件 `<html lang>` 随之宣告给读屏器（`en` / `zh-CN`）。**两档都支持、不夹杂**：

| 已经**逐页**本地化（中英可切、无中文散文残留） | 仍是**中文原生**（界面能切、页面正文未逐字翻译） |
|---|---|
| 侧栏全部 17 个导航 + 3 个分组标题 + 面包屑 + 工作台（#1702）+ 服务状态（#1703）+ 验证列表（#1704）+ 效果评测（#1705）+ 验收契约（#1706）+ 需求覆盖矩阵（#1707）+ 审计轨迹（#1708）+ 用量与账单（#1709）+ 登录连接（#1710）+ 新建验证（#1711）+ 上手指南（#1712）+ 模型连接（#1713）+ 验证详情（#1714） | **旧页面主干 100% 走表**；ui 词表层中文（PARITY 锁死，单独立项） |
| `/tour` — 六卷站整篇双语（`pages/tour.copy.ts`） | |
| `/explorer` — 导语/字段/StatCard/铁证清单全量走表 | |
| `/usage` — 标题/窗口芯片/六张卡/诚实口径句（含 `{basis}` 分母插值）/图例/空账本文案 | |
| `/epic` — 中文六卷原文 + 英文六卷 + 双语尾声（`pages/epic.copy.ts`） | |
| `/lexicon` — 十四条目逐条中英双语（term/gloss/iron/anchor） | |

**原生英文的文档也全部有中文**：`CLAUDE.md` 逐段中英并列（#1696）、`ARCHITECT_CLAUDE.md` 逐段中英并列（#1697）、请查阅 `MCP_GUIDE.zh.md` 等成对手册。

要读《铁证之书》英文全文：`docs/world/EN/SPECROOF_WORLD_EN.md`。

## §5 · 五分钟「最后的诱惑」

1. `#/tour` → 打满六盖印 → 看到红章「验讫」落定 —— 这是你**亲手**把 SpecProof 验收官的盖印付到纸上；
2. `#/explorer` → 用案件档案看见别人的 BLOCKED —— 你读到那一行红字就知道：别人的代码被抓住了，铁证如山；
3. `docs/world/SPECROOF_WORLD.md` → 往下拉，读卷二（审判庭 + 法典）、卷四（微服务军阵）、卷九（印章与窗），每一卷底有**真实提交号**——你可以在 `git log` 里对照查证；
4. `#/usage` → 看到 hit_rate 75-84% …………… 这就是本产品为何不谈「LLM 带宽」而谈「验收效率」。

## §6 · 诚实边界

- 本手册不承诺 100% 功能无毛刺；注明了具体已验证与未验证的边界；
- 本手册的数字（命中率 75-84%、verify 真机 PASS 路径）来自真机实测、账本 `#1650–#1689`；
- 演示仓库（demo/spring-backend）是固定注入缺陷的基准；不是你真实的 PR；
- 未提供参数时：一律**不要**相信 AI 的自信数字；看证据，看铁矩阵，看差分。
