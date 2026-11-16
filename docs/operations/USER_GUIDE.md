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

直接打开 `http://127.0.0.1:5173/`——侧栏已有 39 个一级入口：
> **按 H 打开教学模式**——主界面的按键、按钮、入口各带一句教学说明（金色徽章；悬停/聚焦即可读懂），右下「教学模式」按钮可一键关闭；按 `?` 查看全部快捷键。

| 组 | 入口 | 你能马上做的事 | 铁证 |
|---|---|---|---|
| 工作空间 | 工作台 | 看当天所有验收轨迹 + 未解决的 BLOCKER | — |
| 工作空间 | 变更验收 | 进入 Jobs 列表；点任意一条进详情 | — |
| 工作空间 | AI 开发 | 进入 SpecCraft——让 AI 写代码并自我修复 | LLM 调用 + 自我纠错 |
| 质量与证据 | 需求覆盖 | 看 requirement → contract_id → 判决矩阵 | 真证据 |
| 质量与证据 | 验证规则 | 看每一条契约的 checker_type（http/sql/…） | — |
| 质量与证据 | 效果评测 | 看评测分数（F1/召回/Precision）的真实数字 | 100 例 golden |
| 管理 | 用量与账单 | 看 LLM token 用量 + 缓存命中率（本宿机：aizzz/gpt-6.1-terra·responses） |
| 管理 | 审计轨迹 | 看每一步 audit_logs 写入链路 | 合规 |
| 管理 | 模型连接 | 切换 OpenAI 兼容网关的真实 key | — |
| 管理 | 服务状态 | 健康 (mysql/redis/rabbitmq/minio) + 延迟分布 | — |
| —— | 史诗 | 十七卷竹简式 SpecProof 创世记（卷十五《欠条的钉法》、卷十六《界》） | 全部锚定真实提交 |
| —— | 巡览 | 新用户交互预演（六桩） | 你按了才算数 |

> 没有 .env 也能看 —— 验收不需要 .env 才能视察；需要 `.local/llm.json` 才能跑真实 LLM。

想直接揣一张纸出门？打印 **`docs/operations/POCKET_CARD.md`**——30 秒口袋卡（出门的五件事、四个命令、五个词、出错的时候）。
> English mirror: `docs/operations/EN/POCKET_CARD.en.md`.

### 1.2.1 30 秒自检：demo doctor

```bash
python scripts/demo_doctor.py          # 人读输出
python scripts/demo_doctor.py --json   # 机器可读
```

六个检查（演示仓存在 / `base`、`head-v1` 可解析 / 指向不同提交 / 差异范围合理 /
`demo/requirement.txt` 提及证据族系 / 工作树干净）——全绿再往下走；
任何一条红：先修好 demo 再跑 §1.3，别相信一个坏演示。工作树未提交只警告（`--strict-clean` 可强制转红）。

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

切换侧栏 `缓存健康` —— 本宿机实敲（aizzz/gpt-6.1-terra · responses · stream=True + include_usage=True）：live_lane_probe.py 稳定报 HTTP 200 + cached_tokens=4224；cached_tokens 仅随流式车道上报。
> `hit_rate` 的分母是 `hit_basis_calls`（网关上报了缓存的调用数），不是 `calls` —— 保证诚实。

### 2.3 打开 `#/tour` —— 新手走廊

**六桩真实动作**：每桩都按一下，seal 盖一下；六盖凑齐 → 进度条满 → 出现一句话。
> 全在你 localStorage；谁都代替不了你点。

### 2.4 打开 `#/explorer` — 案卷铁页

点击近期一桩验收 → 看到红印「验讫」，仓库 / 变更 / 开卷日期 / 案卷号，四行 StatCard + AUTH-02 一桩发现 —— **没有一句凭空叙事**。

### 2.5 打开 `#/epic` — 史诗

十四卷竹简 —— 每卷锚死 git 真实提交：卷一（铁证的铸造史）、卷五（史官守夜：#1645、#1668、#1672）、卷六（未完的路：#1722–#1728）、卷七（十二把铁秤：#1730–#1734）、卷八（两种语言的验收：#1740–#1742）、卷九（炉火与河流：#1757、#1758）、卷十（编年史：#1760、#1761、#1762）、卷十一（袖中手札：#1766）、卷十二（证据群岛：#1770、#1771）、卷十三（铁证书房：#1774）、卷十五（欠条的钉法：#1897–#1912）、卷十六（界：#1908–#1912）。**中文版体量见 `#/census`（脚本现推）**。
英文版同构见 `docs/world/EN/SPECROOF_WORLD_EN.md`。

### 2.6 在命令行用 MCP —— 给 AI Agent 当现场法官（`#/mcp` 不是界面页面）

```bash
specproof mcp tools          # 列出 7 个工具
specproof mcp serve          # 启动 stdio MCP server
```
把这个 server 配进 Claude Code / Codex，它们就能把 "我帮你检查这段代码" 变成 `specproof_verify` 调用，而不是信口说。

### 2.7 跑一遍真实 LLM（需要 .local/llm.json）

`.local/llm.json.example` 已在仓库。填入：

```json
{
  "base_url": "https://api.aizzz.xyz/v1",
  "api_key": "sk-…你的key",
  "model": "gpt-6.1-terra",
  "protocol": "chat_completions"
}
```

```bash
# 探针 + 首次真实跑：
specproof probe --base-url https://api.aizzz.xyz/v1 --model gpt-6.1-terra --api-key sk-…
specproof verify --repo demo/spring-backend --base base --head head-v1 --spec demo/requirement.txt --depth FULL
```

> 预期：**与 FAST 模式同样的 BLOCKED**，但这次判决由 GPT 6 sol 亲自下，且 `token 计入 .local/llm_usage.jsonl`。
> 说明（本宿机）：aizzz/responses 车道只随流式 + `include_usage` 上报 usage；非流式模式 cached_tokens 缺省返回——不是网关坏了，是这条线就是接出来的。

---

## §3 · 模块目录（50 页应用）

| 路由 | 模块 | 一句话 |
|---|---|---|
| `/dashboard` | 工作台 | 任务、失败、24h 时间线、blocked 投递盘 |
| `/jobs` + `/jobs/:id` | 变更验收 | 流程化 5 步 RED/GREEN 证据 + capsule |
| `/jobs/new` | 新建验证 | 填 repo/base/head/spec，FAST\|FULL 双深度 |
| `/matrix` | 需求覆盖 | contract_id × evidence_type 表 |
| `/contracts` | 验收规则 | 列出所有契约 + 不知道也能读的解释 |
| `/eval` | 效果评测 | F1/P/R 分类诊断 + golden 对照 |
| `/drill` | 验收快问（闪电问答） | 12 道速测——每题都锚真实文件与真实账本；答完揭晓称号 |
| `/ide` | 铁匠工坊 | 真实锚点 + 抄板 + 炉边便笺，本机落盘 |
| `/graph` | 验收之流 | 18 个 LangGraph 节点逐一拆解：从需求到 capsule | 
| `/chronicle` | 编年史 | 1560 条真实账本条目，一拉到底，永远在长 |
| `/manual` | 说明书（SPECROOF POCKET CARD） | 嵌入 App 的30 秒手札：5 件 / 3 不要 / 5 命令 / 报告词表，可打印可阅读 |
| `/census` | 铁样寨地 | 自研本仓的统计：文件数／LOC／语言 Top 14／账本字节数，全程 git ls-files 派生 |
| `/recall` | 问铁证 | 把账本 1,683 节 + 更正卷轴当作答案库——BM25 现敲：纯本地 · 不联网 · 不调模型 · 分数可复现（引擎页可验模型车道当前关闭） |
| `/atlas` | 世界舆图 | SpecProof 证据群岛地图：三座岛（工作台高原/证据平原/治理海岸）× 24 个厅 + 三条探险路线，防止新人迷路 |
| `/worldbook` | 世界书（铁证书房） | 22 卷正史 + 附录，中英对照，全书搜索高亮，阅读进度本地持久化 |
| `/nightwatch` | 巡夜·子时之后 | 7 站 × 3 滴灯油的快问行走模拟——答案全从 git/账本/世界书现推，通关即「最好的一夜」入册 |
| `/gazette` | 铁证晨报 | 每日发行的仓库报纸：头版故事、最近 24 节、本期数字（全现推）+ 社论，可打印 |
| `/calendar` | 铁证日历 | 过去 365 天每日提交数网格——git log 现推（最忙一天 / 最长连击 / 活跃天数现推） |
| `/billing` | 用量与账单 | 本宿机 aizzz/gpt-6.1-terra 实敲 token + hit_rate（或部署方任选的 OpenAI 兼容服务） |
| `/audit` | 审计轨迹 | 每一步 audit_logs 写入，不丢任何 |
| `/health` | 服务状态 | 6 依赖延迟分布 + 60 面板 SLO 告警触发 |
| `/settings` | 模型连接 | 切换任意 OpenAI 兼容网关（本宿机：aizzz/gpt-6.1-terra · responses） |
| `/agent` | AI 开发者（SpecCraft） | 让 AI 结对把活干完——生成、自修复、失败复盘，全程留痕 |
| `/identity` | 团队与权限 | RBAC、访问控制、审计（admin / operator 角色可见，fail-closed） |
| `/insight` | 洞察舱 | admin / operator 专属仪表盘：合成校准人群 + 本机真实轨迹 + 28 日会话趋势与 7 日预测（r²），以及 6 条引擎规则优化措施（全部明确标注「合成数据」，非真实用户 PII） |
| `/dossier` | 金案谱 | 111 件入库金案逐一可翻：BLOCKER 22 / MAJOR 51 / NONE 38，每案 Severity、Contract、evidence_type、是否应检出——ground-truth.json 当场读取，不经过演示数据、不经过 LLM，可 git show 对照 |
| `/mint` | 印记阁 | 只属于「这个浏览器」的印记：巡览六印、快问阶位、十四式手印、最近脚迹；全部读本地 storage（specproof_tour_v1 / drill_v1 / gestures_v1 / onboarding_v1），不上报、不汇总、不联网，读不出就是「未知」不是零 |
| `/last-call` | 末班车 | 三张独立抽牌：世界书一句抽见 + 金案一次抽见 + 编年史一节抽见——本仓库自己的内容随机出炉，不推荐、不解释、不向任何人献投，每次打开都是新的 |
| `/inkwell` | 墨水池 | 这仓库怎么写自己：总提交 2,456、128 天跨度、深夜下墨占比、周末占比、时辰墨盘 + 52 周潮汐 + 话语权普查——git 审计直读，零姓名、零邮箱，只写节奏 |
| `/gallery` | 卷墙 | 世界书全部 44 卷原文敲门纸罗列成墙：卷号 · 卷目 · 字数段 · 首句——每一块都是 #/worldbook 一本长卷的直接入扣，44 种旅途都从这里开始 |
| `/pulse` | 服务脉搏 | 这个浏览器对它能到达的后端敲一次 /api/v1/health 当场听：时延 ms + 状态/db/llm/embedding/build_sha + 五连敲击 + 本机脉搏留存（localStorage specproof_pulse_v1）。不是舰队 SLA，不撒谎见证 |
| `/trace` | 溯源 | 输入 commit 短哈希、账本节号或任意句子，本页直接扫 1,624 节账本 + 50 卷世界书给你看哪里写过 — 不上传、不联网、只眼观 git JSON |
| `/archive` | 典藏馆 | 全部路由一目了然：正史/史诗 · 验收宫 · 入口 · 静水对鉴 · 服务 · 管理员回廊 — 37 一级入口全图示 · 每张牌连真实路由 · 直读 git JSON · 永不迷路 |
| `/engine` | 引擎 | 本仓库真实往复 aizzz/gpt-6.1-terra 的 prompt/completion/cached tokens 全部来自 .local/llm_usage.jsonl，nothing else · p50/p95 真延迟 · 直读 byte 数，不估计一行 · 不是 marketing page |
| `/fabric` | 织物 | 仓库的全部房间展开在一幅织物上：37 节点 · 7 经线（正史 / 验收宫 / 入口 / 静水对鉴 / 服务 / 管理员回廊 / 本地探天窗）· 点击节点直达对应路由 |
| `/exhibits` | 实测回廊 | 本仓库亲压自己 front door 的每一击 · 并发 / 判决 / worst p99 · 每一条锚回 exhibit #N · exhibit #4（1,526.1 ms）永在册 · Night Watch 永远 CRACKED；全是 git log 真敲实测 |
| `/ui-kit` | 设计系统 | 全 Aurora 组件对照 |
| `/epic` | 史诗 | 十八卷创世记，每卷锚死 git 哈希 |
| `/tour` | 巡览 | 新手交互式走廊，六盖一齐验讫 |
| `/explorer` | 案件档案 | 铁证装订 - 红印验讫封面 |
| `/lexicon` | 铁证词典 | 十四个词，每词可搜、可点开、锚到仓库真实位置 |
| `/gestures` | 验收官十四式 | 十四种验收站姿一网打尽——可敲盖、见铁印 |
| `/museum` | 铁证博物馆 | 十二件实证展品，每件锚到账本真实条目 |
| `/errata` | 更正卷轴 | 十六条误判留痕（R01–R16），每条锚到账本号与 commit；查询只寻不删 |
| `/stategraph` | 状态图谱 | 这本仓库里的六张 LangGraph StateGraph（recall/evidence/purity/auditor/night_watch/cache_witness）+ 读图八词；现场判词原样上屏 |
| `/usage` | 缓存健康 | 真 hit_rate + 计费链条 |
| `/guide` | 上手指南 | 从 clone 到第一个 BLOCKED 的 4 步 |
| `/login` | 连接 | API key / Bearer —— 无 key 时每个页面都回到这里 |

> 两点说明：
> - **MCP 工具不在界面里**：命令行 `specproof mcp tools`（§2.6）+ 文档 `docs/operations/MCP_GUIDE.zh.md`；界面没有 `#/mcp` 页；
> - `#/findings/<job_id>/<finding_id>` 是深链页面——在任务详情里点 Finding 进入；`/ui-kit` 是懒加载路由。

---

## §4 · 中英文切换（if the screen shows mixed colours of text）

顶栏**语言切换钮**（显示 `EN` / `中`）随时可切；选择存本机 `specproof_locale`，刷新后保留；
文件 `<html lang>` 随之宣告给读屏器（`en` / `zh-CN`）。**两档都支持、不夹杂**：

| 已经**逐页**本地化（中英可切、无中文散文残留） | 仍是**中文原生**（界面能切、页面正文未逐字翻译） |
|---|---|
| 侧栏全部 39 个导航 + 3 个分组标题 + 面包屑 + 工作台（#1702）+ 服务状态（#1703）+ 验证列表（#1704）+ 效果评测（#1705）+ 验收契约（#1706）+ 需求覆盖矩阵（#1707）+ 审计轨迹（#1708）+ 用量与账单（#1709）+ 登录连接（#1710）+ 新建验证（#1711）+ 上手指南（#1712）+ 模型连接（#1713）+ 验证详情（#1714） | **旧页面主干 100% 走表**；ui 词表层（toneMap / errorHints / stages / preflight）已全部**中英双语**（#1730/#1732：gloss 随 locale 解析，parity 门继续锁两表对称） |
| `/tour` — 六卷站整篇双语（`pages/tour.copy.ts`） | |
| `/explorer` — 导语/字段/StatCard/铁证清单全量走表 | |
| `/usage` — 标题/窗口芯片/六张卡/诚实口径句（含 `{basis}` 分母插值）/图例/空账本文案 | |
| `/epic` — 中文十七卷原文 + 英文十七卷 + 双语尾声（`pages/epic.copy.ts`） | |
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
