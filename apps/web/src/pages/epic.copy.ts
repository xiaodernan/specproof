import type { Locale } from "../i18n/strings";

/**
 * The English edition of the Epic page's fourteen scrolls.
 *
 * The Chinese edition lives inline in `Epic.tsx` (it is the original text of
 * the book); the English edition is kept beside it so both languages can be
 * read side by side without either drifting from the other's shape.
 * Every anchor in the details lists is a real commit in this repository.
 */

export interface ScrollDetail {
  label: string;
  value: string;
}

export interface Scroll {
  num: string;
  title: string;
  en: string;
  era: string;
  verses: string[];
  details: ScrollDetail[];
}

export interface ScrollDetail {
  label: string;
  value: string;
}

export interface Scroll {
  num: string;
  title: string;
  en: string;
  era: string;
  verses: string[];
  details: ScrollDetail[];
}

export const SCROLLS_ZH: Scroll[] = [
  {
    num: "卷〇",
    title: "创世·一炉铁证熬成",
    en: "The Furnace of Evidence",
    era: "2026-09 · 立项",
    verses: [
      "世人叫 AI 写代码，代码写完便是「好了」。验收官说：不成——先有证，再有判；先有铁，再有符。",
      "于是创世之炉开张：验收不问天意，只问铁证。证据者，可复现之物也；可复现者，方为真相。",
      "凡欲过此炉者，必历三道火：先有契约为绳、再有差分为镜、最后以矩阵定罪。三火俱过，方许盖「验」字。",
    ],
    details: [
      { label: "差分验证内核", value: "base → head 双侧同机复现，结论落在 base_pass_head_fail 等证据类型上" },
      { label: "契约编译器", value: "http · sql · redis · openapi · rabbitmq 五类 checker，needs{…} 方法均有单测锁住" },
      { label: "裁决纪律", value: "AI 不做判决；severity 由确定性策略复算，模型的「我觉得」在此不值钱" },
    ],
  },
  {
    num: "卷一",
    title: "铁证·矩阵列罪",
    en: "The Matrix of Iron Evidence",
    era: "2026-09 ~ 2026-10 · 证据体系",
    verses: [
      "证据分五等：Java 源码差分、静态分析、契约检查、探针差分、以及——唯一被称为「铁」的 base_pass_head_fail。",
      "铁证乃是：合并前基线测试全绿、合并后目标测试全红。一正一反，落在同一个机头上，无可抵赖。",
      "审判庭（review_court）不过是一场夜审：对抗的双方各持证据上台，最后由确定性策略复算刑名——事实本身判案，不由口才判。",
    ],
    details: [
      { label: "golden 案例", value: "head-v1 演示场景：UserController.java 移除 @PreAuthorize —— 最诚实的注入式回归" },
      { label: "探针防伪", value: "9 例反例计数锁、severity 漂移《#1654》式重钉，假发现绝不入账（#1638 全线）" },
      { label: "执行面披露", value: "execution_surface 字段强制携带于每一条 finding —— 证据在哪跑出来的，永远说明白" },
    ],
  },
  {
    num: "卷二",
    title: "双端·前进队与粮草官",
    en: "The Twin Vanguards",
    era: "2026-10 ~ 2026-11 · 前后端合龙",
    verses: [
      "验收官坐在案前，需要看两样东西：案卷，和证人。前端，就是那位给你递案卷的书记官。",
      "于是书记官学会了逐字说话：SSE 进度流、阶段时间线、AI 解读一字一字落下来的墨迹、Markdown 摘要可一键装进评审帖子里。",
      "打印稿也讲究：每一页纸都必须配得上「铁证」二字——留白、条款、签章，一样不能少。",
    ],
    details: [
      { label: "阶段时间线", value: "执行阶段按时间轴渲染；无时间戳的阶段如实列在下方，绝不编造位置（StageTimeline，5 腿单测）" },
      { label: "AI 解读增量流", value: "SSE 逐字到达 + 缓存重放；断流时保留已到文本并如实报错（#1665）" },
      { label: "复制即分享", value: "「复制 Markdown 摘要」把一次验收的证据装进任意评审帖子（#1664）" },
    ],
  },
  {
    num: "卷三",
    title: "算力·缓存命中那场仗",
    en: "The Cache Doctrine",
    era: "2026-11 · 计费圣殿",
    verses: [
      "算力如潮水。潮来则费十倍，潮退则零散成滴。智者不拦潮水，只教每一朵浪记住前一朵浪的方向。",
      "于是创世的铁的纪律落成：稳定前缀在前、可变内容在后，prompt 不是散文，是缓存键。",
      "双车道统一流式 + include_usage，缓存命中终于能被计费看见——token 不再无声流走。",
    ],
    details: [
      { label: "流式统一", value: "legacy 车道 #1644、policy 车道 #1663：网关仪表盘从此没有「非流」" },
      { label: "计费口径", value: "cached_tokens → prompt_cache_hit_tokens → 0.1× 权重入账（#1644）" },
      { label: "现场实测", value: "_JUNIT_GENERATION_PROMPT 前缀 2272B，42.1s → 9.1s，命中率 96.5%（#1645，如实）" },
      { label: "A/B 复核", value: "#1668：换变量后 Wkapi 今日报 None——账本并列两组数据，不伪造结论" },
    ],
  },
  {
    num: "卷四",
    title: "军阵·钢铁长城立起来",
    en: "The Steel Rampart",
    era: "2026-11 · 微服务",
    verses: [
      "单兵不成阵。验收官要各安其位：边缘为门、登记册为目、法典库为藏、断路器为卫——谁也谁代不了谁。",
      "Eureka 把每个进程登记成名字：specproof-gateway。config-server 把每一处配置收到同一本书里。网关只认一条路由表，谁敢擅动，算路由表不同构。",
      "断路器如关城闸：上游死了，它闭闸不摊牌；没到阈值，它不宣判；它打开，就是它说了。",
    ],
    details: [
      { label: "Eureka 注册", value: "discovery-server 8769、register-with-eureka、Gateway 192ms 注册（2026-11-14 实录，#1674）" },
      { label: "边缘断路器", value: "死掉的上游连打 12 次：state closed → open（第 5 次起），`/api/v1/tenants` 503 而不卡死（#1674）" },
      { label: "Config 热刷新", value: "POST /actuator/refresh → 见证器 `specproof_edge_config_refresh_events_total 0.0 → 1.0`（#1673/#1674）" },
      { label: "健康铁律", value: "RabbitMQ 是 opt-in 总线——broker 不通不应把 /health 打成 DOWN（与 Redis 同构的既有纪律）" },
    ],
  },
  {
    num: "卷五",
    title: "史官·一书不毁、一证不添",
    en: "The Append-Only Ledger",
    era: "贯穿 · 治理之道",
    verses: [
      "史官只做两件事：写下发生过的事，绝不涂改已经写下的。",
      "每一个「已完成」都有一笔账可查：命令、输出、时间、真相——账本不替人脸上贴金，也不替失败寻找借口。",
      "至于「证明给自己看」的冲动——也写进去。探针 A 把披露埋进合并层，红了九例；探针 B 把修法退回去，红了四例。锁是真的，不是编的。",
    ],
    details: [
      { label: "append-only 账本", value: "docs/operations/DEEP_OPTIMIZATION_PLAN.md —— #1620 → #1674，每笔都附实测命令与输出" },
      { label: "账本之门", value: "IDs 唯一、编号唯一、队列指针可解、证据断言为真——四道门缺一不过" },
      { label: "e2e 说真话", value: "openEventStream 把 `event: done` 帧的 data 静默丢弃——AI 解读永远停在「正在解读…」；e2e 抓出并修复（#1672）" },
      { label: "不装绿", value: "被并轨车道锁住的部分直接接手；无法证伪的一律标注边界，绝不伪装成功" },
    ],
  },
  {
    num: "卷六",
    title: "未完的路",
    en: "The Unfinished Road",
    era: "2026-11 · 至今",
    verses: [
      "欠条不是羞耻，是地图；地图上的每一块空地都有名字。",
      "门面不撒谎，数据不充值；每周日 06:00，展柜才挪动一寸。",
      "史官把没做完的写在墙上——全量测试没跑绿，也不许粉饰。",
    ],
    details: [
      { label: "未竟的卷", value: "世界书卷十五落地（#1727）：六块空地逐条写「做完长什么样」，终章从此有了下一页" },
      { label: "门面的约定", value: "portfolio-sync 每周外送 data/specproof-* 三件套（#1722）；没有 PORTFOLIO_TOKEN 就只重建不推送" },
      { label: "真相的一课", value: "wkapi 的 96.5% 缓存命中率是网关 4224 常量计费，降级为观测指标（#1723）；provider_smoke 真跑 7/7 PASS（#1724）" },
      { label: "地基的自检", value: "demo doctor 六项静态检查，工作树脏则如实 WARN（#1728）；指南幽灵路由清零并有 gate 锁死（#1726）" },
    ],
  },
  {
    num: "卷七",
    title: "十二把铁秤",
    en: "The Twelve Iron Scales",
    era: "2026-11 · 至今",
    verses: [
      "舌头有两种颜色时，铁证只有一种颜色——按下去，该响就响。",
      "错题不是终点，错题回炉才是练武的真火。",
      "从「它声称双语」到「toggle 一按就换脸」，中间隔着 147 个词条和一次不删测试的修表。",
    ],
    details: [
      { label: "147 个词条", value: "toneMap/errorHints（#1730）+ stages/preflight（#1732）全部随 locale 解析；i18n parity 双向锁两表对称" },
      { label: "十二把铁秤", value: "#/drill 验收快问（#1733）：12 题锚真实声明域与账本；四阶封印；497/497 vitest 全绿" },
      { label: "基线红到真绿", value: "verdict_channel_parity 在 master 上本就是红的——api/ai_summary.py 登记为 job_summary 搬运工（owner+opaque），从此真绿（#1730）" },
      { label: "幽灵路由清零", value: "/mcp、/admin/identity、/readme 从两本手册消失；guide-route-catalog gate 永世锁死（#1726）；#1732「键写反」事件如实入史" },
    ],
  },
  {
    num: "卷八",
    title: "两种语言的验收",
    en: "The Two-Tongued Verdict",
    era: "2026-11 · 至今",
    verses: [
      "对用户说两种语言，对机器也说两种语言，对账本只说真话。",
      "缓存不是承诺——它会翻旗；红灯不是心情——它是颜色。",
      "机器签名先看 tag 在不在；承诺先立锁，再谈合并。",
    ],
    details: [
      { label: "同题同答", value: "#1741：gpt-6-sol.zh→BLOCKER(4749 tokens, cached 3981)，en→BLOCKER(4727 tokens, cached None)；CONSISTENT——双语 UI 不是想象的双重承诺" },
      { label: "探针不作 gate", value: "双语一致性只结账不定罪：不一致只会入账 divERGENT，绝不把观测升为判决（与 #1723 同款纪律）" },
      { label: "CI 守手册承诺", value: "#1740：.github/workflows/demo-doctor.yml；master push/PR；fetch-depth:0 保住 base/head-v1 tag——浅克隆会把真闸门变假警报" },
      { label: "缓存的活案底", value: "同一轮探针 zh cached=3981 vs en cached=null——#1723 的按语仍然成立：命中率是表，不是契约" },
    ],
  },
  {
    num: "卷九",
    title: "炉火与河流",
    en: "The Forge and the River",
    era: "2026-11 · 至今",
    verses: [
      "炉火不会替你干活，它只能保证你从它身边走过时，手里接到的全是真铁。",
      "一张屏幕没法替代一台机器——它唯一的用处是把五样东西放在同一张桌上：光、铁、火、故障与真相。",
      "河的真名叫状态机：每一滴水进来就是一个 state，出去就是一份证据。",
    ],
    details: [
      { label: "铁匠工坊 #/ide（#1757）", value: "锚点 Rail 六件实物 + 抄板五条真命令 + 便笺 localStorage 落盘；云 IDE 不存在——FastAPI 静态托管同一份 SPA 而已" },
      { label: "河流 #/graph（#1758）", value: "agent/graph.py::build_phase0_graph() 的 18 节点状态机，两条条件边如实显示；浏览器永不运行 Python" },
      { label: "真验证过的 RAG（#1757）", value: "scripts/repo_rag.py：纯 Python TF-IDF，142 篇 markdown 检索到 top-5 → wkapi/gpt-6-sol；实测答对缓存命中率论题并 cite POCKET_CARD" },
      { label: "/health 59 秒变一半（#1755）", value: "MySQL+Redis 探针原串行：DEAD 后 29s，并行后 27s——收益有限，诚实记录，收据里没吹牛" },
    ],
  },
  {
    num: "卷十一",
    title: "编年史",
    en: "The Chronicle",
    era: "2026-11 · 至今",
    verses: [
      "史官每天清早起床，先检查茶壶是不是满的——因为没写完的东西不是卷轴，是待办。",
      "一本编年史永远是未完成的：谁合了 PR，谁就要重新跑一遍；不是懒得跑，是跑出来的才算数。",
      "没有史官敢说「账本说了算」。账本只说它知道什么，不会替任何人宣称它已经完成了。",
    ],
    details: [
      { label: "build_chronicle.py（#1761）", value: "纯 stdlib：解析 DEEP_OPTIMIZATION_PLAN.md 的 `## #NNNN` 节 + 正文首个有意义句，输出 apps/web/src/pages/chronicle.json；1561 节、#130→#1760" },
      { label: "chronicle.json（#1760）", value: "~259 KB，每行 = 节号 + 标题 + 首个有意义句；首节从 #130 起——早期竹简由史官自己不给自己写" },
      { label: "编年史页 #/chronicle（#1760）", value: "竖线编年体：搜条目/正文/编号，#NNNN 自引用也支持；连编都合进 history，跑起来不骗你" },
      { label: "史官的两条法律（卷十九）", value: "《它做了 X》or《它没做 X》——没有第三句；编年史不是永动机，改变即重跑 build_chronicle.py（不自动）" },
    ],
  },
  {
    num: "卷十二",
    title: "袖中手札",
    en: "The Pocket Manual",
    era: "2026-11 · 至今",
    verses: [
      "袖子里不装剑，装一张纸——一张写清「出门前必须知道」的纸。",
      "证据不先于人，人就会先决定；手札不先于门，客人才忘自己正走向哪里。",
      "手札不是小册子，是「这一次我没忘」。",
    ],
    details: [
      { label: "说明书页 #/manual（#1766）", value: "SPECROOF POCKET CARD 在 App 内复现——A4 printable white paper + 金横杆 + 中英双语；打印即合格上路纸卡" },
      { label: "手札三件套（#72、#1702 以来）", value: "#/guide（按部就班） · #/tour（六盖印通关） · #/manual（一张纸）——不是替代，是同章的三节" },
      { label: "口袋卡就是化人为律音", value: "不是教学幻灯——五件进门事实 + 三个不要 + 五条命令（全部本仓真实）——读完，它记在你的手上，不在你的脑子里" },
      { label: "纸卡有一个秘密", value: "它永远折叠在你的口袋里——但它永远知道你昨天读了哪一本书，今天还没读哪一条律" },
    ],
  },
  {
    num: "卷十三",
    title: "证据群岛",
    en: "The Evidence Archipelago",
    era: "2026-11 · 至今",
    verses: [
      "世界大到走不完，不等于你必须迷路——给每个来客画第一张图，就是这片世界的待客之道。",
      "一张地图上三座岛：工作台高原、证据平原、治理海岸——二十四间大厅分别落座。",
      "比例尺上刻着真实提交：0、1,000、2,000、2,400+——这张图不撒谎，因为它脚下踩的是 git。",
    ],
    details: [
      { label: "世界舆图 #/atlas（#1770）", value: "SPECROOF ATLAS——三岛 × 24 厅 + 三条探险路线 + 活体地标（git ls-files 现推）" },
      { label: "目验与入框（#1771）", value: "bbox 数学目验：三岛落框、N 入表盘、题词入缘——没有一件零件越出发框" },
      { label: "三条探险路线", value: "快速上岸 90 秒（tour→manual）· 证据考察 25 分钟（epic→chronicle→census）· 验收实战 10 分钟（jobs/new→matrix→FindingDetail）" },
      { label: "地图不是代替探索", value: "它是通往探索的门廊——看懂地图的人，才敢踏进平原；画不出岛的，是沙，不是洲" },
    ],
  },
  {
    num: "卷十四",
    title: "铁证书房",
    en: "The Reading Room",
    era: "2026-11 · 至今",
    verses: [
      "一本值得终身保存的书，不该躺在终端里——正史该有自己的房间，书房该有页码和书牌。",
      "二十九节逐字上架：序章、卷零到卷二十二、附录甲到附录丁、终章——每一字都能拿和仓库对照。",
      "书房里的每一卷，读到了就是你的国土；没读到的，永远在等你推门。",
    ],
    details: [
      { label: "铁证书房 #/worldbook（#1774）", value: "29 节（序章 + 23 卷 + 附录 ×4 + 终章）中英对照 · 全文搜索 <mark> 高亮 · 进度本地持久化 · 随机开一卷" },
      { label: "书房的原料只有一座", value: "docs/world/SPECROOF_WORLD.md（zh）与 EN/SPECROOF_WORLD_EN.md（en）——build_worldbook.py 一字不改地上架" },
      { label: "书房不是展厅", value: "不是陈列，是阅读—— marked 渲染表格/代码/引用；搜索命中 2 处即刻点亮；读完一卷按一次「已读完本卷」" },
      { label: "书房会老", value: "合一次 master 重跑 scripts/build_worldbook.py，书才不褪色——世书更新的节奏，就是书房亮灯的节奏" },
    ],
  },
  {
    num: "卷十五",
    title: "欠条的钉法",
    en: "The IOU Epigraph",
    era: "2026-11 · 至今",
    verses: [
      "一张欠条不是羞耻——它是地图；每一处空白都有名字、有账本编号。",
      "2026-11-16 这一天，owner 亲笔一行：「把这些全部做了，我全部批准。」——OBSERVABILITY.md §9 签字落了；分身的 D2（PORTFOLIO_TOKEN）依然欠着。",
      "铁证可以不眨眼：exhibit #4 永远留在那里，Night Watch 今晚的判词是 CRACKED——没人求它绿。",
    ],
    details: [
      { label: "D1 已签落 · OBSERVABILITY.md", value: "owner 授权（#1897）落字；signature block found，identity 未加密实证——如实入册，不涂成 verified" },
      { label: "D2 仍未还", value: "PORTFOLIO_TOKEN 在你自己的 Secrets 里；本仓不 mint。工作流周日 06:00 UTC 敲门：products.json · latest.md · .github-sync.json 三件静默待主" },
      { label: "Night Watch 的红", value: "exhibit #4（1,526.1 ms）与 exhibit #8（2,078.7 ms）永远挂在 /engine；Δ>25 ms 铁规不动（#1890）；exhibit #9（64c · p99 1,596.9 ms · #1912）已入册" },
      { label: "R14 的邮戳", value: "出网没挂梯子时全红（区域封锁）；挂 Clash Verge（7897）后真跑通：HTTP 200 · 9 chunks · cached 4224 → 6400（#1884）" },
    ],
  },
  {
    num: "卷十六",
    title: "界",
    en: "The Screen That Speaks One Language",
    era: "2026-11 · 至今",
    verses: [
      "一个屏幕说两种话，不是双语——是噪音；中文模式全中文，英文模式全英文。",
      "状态图不是装饰——它是契约：八张图在线跑，判词 fail-closed；Night Watch 永远 CRACKED。",
      "铁证之书的每一页都能被敲开：/errata 是十六条亲笔更正，/stategraph 是八词说明书和八张活着的图。",
    ],
    details: [
      { label: "纯度闸已上 · i18n.purity.test.ts", value: "en 零 CJK / CJK 标点 / 全宽；zh 零英语连词三连——随 vitest 生效（#1909）" },
      { label: "更正展厅 /errata", value: "R01–R15 · 全双语 · 可搜索 · 每条钉提交；查询只寻不删（#1908）" },
      { label: "状态图谱 /stategraph", value: "八词教材 + recall/evidence/purity/auditor/night_watch 五张活图 + 夜巡判词 verbatim——CRACKED 不涂（#1910）" },
      { label: "溢出保护层", value: "h1 任意换行 · media max-width · pre overflow-x；不藏组件，只加滚动（#1911）" },
      { label: "两道门影 · 8888 影子", value: "control-plane test profile 被遮蔽 prometheus/refresh → exposure pin 落（#1912）；mvn -o 137/137 复敲 GREEN" },
      { label: "第六张图 · /stategraph", value: "cache_witness_graph 落册：同一固定提示连敲两下 · cached_tokens=4224×2 · hit_rate 95.3% · HIT——本仓唯一出网的一张图，按设计敲模型车道、朝你数缓存；/stategraph 六张活图（#1933）" },
      { label: "洞察 AI 解读 · /insight", value: "Insight Deck 加「AI 解读 · 数据怎么说下一件事」：admin/operator 让 aizzz/gpt-6.1-terra 读这块面板的匿名聚合数——allowlist 裁剪包（零 PII）· 首敲 730 字节 · 模型延迟 17,032 ms · 如实引用 201→113 / 84→41 · 自发说「本包数据不足以判断」 onboarding_routes=0；RBAC 不动（#1936）" },
      { label: "模型自己写补丁 · craft×aizzz", value: "free-form 中文需求「修复 double 函数的逻辑错误」→ plan.mode=llm · 四步中文计划 · 模型自己写下 x / 2 → x * 2（无 fix_registry）→ LOOP_RESULT=DONE → **验收 BLOCKED**（本机 Docker python 缓存缺 pytest · No module named pytest——门没动，补丁回滚，世界回 base）· cached 4224 命中在第二次调用（#1937）" },
      { label: "砂箱咬住 pytest · #1938", value: "砂箱三段式合成落册：venv → wheelhouse 离线装机（pytest 9.2.0 已播种）→ pytest（effective docker mode 才重写）· local 模式一字不动 · 25/25 runner 断言 · **run_test 首次全绿**（155 s · exit 0）· Docker Desktop 曾当场死一次（unexpected EOF）如实在案；SpecProof 验证器 REJECTED（Java/Maven-first · No pom.xml）——墙的名字被写下（#1938）" },
      { label: "Δ 对最早一篇 · #1939", value: "exhibit #14（2026-11-16T17:48Z · 48c ×2×4）落册：err 0.00% · 最糟 p99 1,074.4 ms · OK；对最早一篇 exhibit #2（2026-11-15T17:28Z）核 Δ——p99 −462.9 ms · p50 约 2.5× 抬升 · 只记录不吹；exhibit_entries 14 → 15（#1939）" },
      { label: "384c · #1940", value: "exhibit #15（2026-11-16T17:56Z · 384c ×2×4 rounds + 3 warmup）落册：rounds err 4.43/2.34/4.30/4.04% · p50 ~530–547 ms · 最糟 p99 2,061.0 ms · BUDGET-BLOWN——192→256→384 今晚不成单调（64–70% → 34–45% → 2–4%）· 饱和曲线 x 轴加 384c；exhibit_entries 15 → 16（#1940）" },
      { label: "第七张图 · #1942", value: "insight_advice_graph.py 落册：intake → strike → verdict → report → END——盯洞察舱模型车道，「ANSWERED」即唯一表态；实敲 ANSWERED · latency 46,519 ms · cached 0（Prefix 不同）——七张活着的图（5 离线 + 2 出网）/stategraph 挂牌（#1942）" },
      { label: "红门只打三扇 · #1945", value: "设计系统门四道：4px 台阶／字阶／圆角／阴影计数 HEAD 608→0 / 406→0 / 101→0 / 71→0 · 颜色字色结构未动，1165 在册（字面量等语义命名） · Night Watch 依旧 CRACKED · exhibit_entries=16 · 改计数，没动阈值（#1945）" },
      { label: "撞门的人 · #1944", value: "rate-limit 钉死：SPECPROOF_RATE_LIMIT_PER_MIN 默认 5/min · specproof:rl:<sha256(key)[:16]>:<window> · incr→count==1 expire(90) · count>limit ⇒ 429 RATE_LIMITED · fail-open=声明不是bug · 32 连发错误钥全 401 · tests/unit/test_rate_limit_fixed_window.py 3/3（#1944）" },
      { label: "红门又掀开半扇 · #1946", value: "theme-blind 字色总门 1,165→593：逐站实敲 pytest · 辉光/brass/parchment/steel 命名 · tokens.css 两次写浮后「双 pass 纪律」立册 · exhibit_entries=16（#1946）" },
      { label: "门全绿了 · #1947", value: "theme-blind 字色总门 593→**0**：463 枚 --pigment-* token 逐字节登记 · 13 枚 context-invariant 复用（--print-* 一律不复用）· design-system 家族至此全部落窗 · 4 px 网格/圆角/字阶/阴影/字色 0（#1947）" },
      { label: "同一本账 · #1948", value: "LLM 缓存账按车道×协议双轴拆开（by_lane direct 0.5418 / policy 0.0 · R16 有机器数据背书）· Usage 面板新增双表面板 · +3 honesty 测试（#1948）" },
      { label: "粗筛的尺子 · #1949", value: "i18n 全量审计升级：bucket A 366→196→**138** · 新增 bucket C（L()/zh?/{ zh: }/…_ZH 同行成对双语 1,172 条归位）· 只降噪不放行 · audit 永远 exit 0 不进 CI（#1949）" },
      { label: "第八张图 · #1950", value: "usage_ledger_graph.py 落册：intake → strike → verdict → report → END——离线读本机 token 级用量账本，同一套 Usage 面板的口径；现场判词 ANSWERED · window 24h · 38 次调用 · 6 次错误 · hit_rate 0.430（basis 32）· 八张活着的图（6 离线 + 2 出网）/stategraph 挂牌 · 判词 ANSWERED/UNAVAILABLE 沿用 witness 词表（#1950）" },
      { label: "第九张图 · #1954", value: "investigation_dig_graph.py 落册：explorer/tester/security 三只只读 investigators 并行敲模型一个 question——实敲 aizzz/gpt-6.1-terra · 判词 EVIDENCE-GATHERED · /stategraph 九盏活图挂牌 · StateGraph.test 8/8（#1954）" },
      { label: "The Dig · #1955", value: "/api/v1/admin/investigation-dig + /dig 页面：同一套只读 investigators 并行敲本仓（bounded fact pack ≤4 KB）——现敲 aizzz/gpt-6.1-terra (经 Clash Verge) · verdict EVIDENCE-GATHERED · 16,200 tok · UI 576/576（#1955）" },
      { label: "见证人也得自签 · #1957", value: "witness channel 扩编：owners 19→23 · opaque 19→23 · witness pointer craft/investigators.py:294 · verdict-channel parity 回到 14/14（#1957）" },
      { label: "每扇红门重敲一遍 · #1958", value: "全量巡检：26 红 → 24 红（23 条 payload-census 家族按 #8 照册不动 · 1 条 U+FFFD @ ledger:40823——那个字节恢复不了也不许我写假字）· mypy 289/289 · mvn -o 两 service BUILD SUCCESS · 5 触发面齐同步（guides/RBAC/scrape 直连 lane SpecproofLocalHostApiDown 探针 · FAKE_INVENTORY pin → b7a011a · demo-marker ×2 改判 copy pack）（#1958）" },
      { label: "值班手册 · #1959", value: "runbook_triage_graph.py / /api/v1/admin/runbook-triage + Runbook 页面：探针一响模型先读仓库（alert rule × 最近 20 提交 × 最新 5 份 evidence × compose 的脱敏 api env）· 判词 CONFIRMED / INCONCLUSIVE · /stategraph 挂第十张（十张活图）· UI 580/580（#1959）" },
      { label: "术语自己会收口 · #1960", value: "glossary 长出三个 Runbook 词条：dig（深挖现场）· runbook（值班手册）· inconclusive（证据不足）· Runbook 页面的两处术语原生悬浮解释 · UI 580/580（#1960）" },
      { label: "观察舱 · #1966", value: "/observe 公开·只读·演示公开页：240 人合成校准群体 + 本机真实轨迹 · r²/斜率/漏斗双语 · 密码「123」放开模型现场解读（live 后端车道 · 指纹缓存）· 永不含真实人数据 · UI **587/587**（#1966）" },
      { label: "真一台 · #1967", value: "/observe「本机这一台」面板：浏览器 `specproof_heat_v1` 真实气候（点按 · 秒退 · 急躁 · 中位停留）· 不上传 · 沉默不是零 · 模型车道仍只读匿名聚合 · UI **589/589**（#1967）" },
      { label: "不夹的章 · #1968", value: "i18n 夹杂收口八处——zh 分支不长英尾巴 · A 桶 37→29 · UI **589/589**（#1968）" },
      { label: "行宪 · #1969", value: "`api/system_covenant.py`——字节恒定中文宪章 1,450 B（11 法 · 钉住仓库真件）· 五车道共享 · 法院车道不带 · 缓存现状如实登记 · UI **589/589**（#1969）" },
      { label: "活数字 · #1970", value: "Archive 三卡接活值：世界书 **171** · 墨水池 **2,643**（span 130 d · streak 16）· 金案 **111** · inkwell.json 重敲入库 · UI **589/589**（#1970）" },
      { label: "行宪见证人 · #1971", value: "/stategraph 第十一盏「行宪见证人」· sha256 pin 住 #1969 行宪日 · 永不敲模型 · parity **14/14** · UI **590/590**（#1971）" },
      { label: "自己的证券 · #1972", value: "全量 32 红逐名对账 · 5 红门当场修复（parity · 4px grid · D08 knob · fake-inventory pin · closure client 桶登记）· payload-census 钉实证 23→22 · UI **590/590**（#1972）" },
    ],
  },
  {
    num: "卷十七",
    title: "守夜人手里的灯",
    en: "The Night Watch Inside the Badge",
    era: "2026-11 · 至今",
    verses: [
      "夜里没人敲门时，守夜人也不会停—— exhibit #4 永远钉着，Night Watch 判词永远是 CRACKED。",
      "网关说过「缓存命中了一次」（4224）——史官记录了那一次，也记录了之后两次「0/0」。说「改善」的不是史官。",
      "夜不是因为被守住才安静，而是因为守夜人一次也没让眼睛闭上。",
    ],
    details: [
      { label: "exhibit #9 · 64 并发", value: "512 req · err 0.00% · worst p99 1,596.9 ms（填补 #7〔48c〕#8〔96c〕之间的空心）— Night Watch 依然 CRACKED（#1912）" },
      { label: "两道门影 · 8888", value: "control-plane 两个 actuator 测试被宿主 8888 旧 config-paney shadowed → 404 ×2（prometheus/refresh）→ test profile 钉 exposure include 全（gateway 同防）；mvn -o 137/137 复敲 GREEN（#1912）" },
      { label: "R16 · 第十六枚", value: "two_strike_probe.py（scripts/）同 prompt 连敲两次 → prompt_cache_hit_tokens 0/0；R16 入册：一次 4224 hit ≠ 命中率。/errata 计数 16（#1915）" },
      { label: "README 真相重绘", value: "README / README_EN 模型表 stale 段（ynynzyy·gpt-6-astra · wkapi.pro·gpt-6-sol）全替换为 api.aizzz.xyz/v1·gpt-6.1-terra·protocol responses·max — Clash Verge 127.0.0.1:7897；注释 R14（#1916）" },
      { label: "Collect 门放行", value: "routerSmoke 43 NAV 路由× zh/en 真挂载·render-crash 断言·bomb /graph 双语双红定位至路由 · 复绿即绿； UI 559/559（#1914）" },
    ],
  },
];

export const CLOSING_ZH = [
  "尾声 · 未完",
  "史官的本子翻到这页，只道一件事：没写完。路线图还有项未静声：1.3 演示自检、1.6 Verify 解耦、4.2 反例裁决、5.3 可观测开箱、5.4 部署形态、6.1 IDE/CI 集成——每一笔都写着下一步的名字。",
  "铁证不因多而更硬，也不因少而失重。验收官若问「我能信它吗」，答案永远不在卷首，而在卷末：铁证，自证。",
];

export const SCROLLS_EN: Scroll[] = [
  {
    num: "Scroll 0",
    title: "Genesis · A Furnace for Iron Evidence",
    en: "The Furnace of Evidence",
    era: "2026-09 · founding",
    verses: [
      "The world calls it AI writing code; code written, they say, is done. The Acceptance Officer says no — first the evidence, then the verdict; first the iron, then the seal.",
      "So the furnace was lit: base and head were cooked in the same sandbox, and the flame leaned one way or the other. A flame that leans back means the baseline was safe; a flame that leans forward means the future is on fire.",
      "Nothing passes this furnace without iron. That iron has a name: base_pass_head_fail.",
    ],
    details: [
      { label: "Differential core", value: "base → head replayed in one sandbox; the verdict lands on evidence types like base_pass_head_fail" },
      { label: "Contract compiler", value: "http · sql · redis · openapi · rabbitmq checkers, every needs{…} method unit-tested" },
      { label: "Judgement discipline", value: "the AI never judges; severity is recomputed by deterministic policy — its opinion is worth nothing here" },
    ],
  },
  {
    num: "Scroll 1",
    title: "Iron · The Matrix Lists the Charges",
    en: "The Matrix of Iron Evidence",
    era: "2026-09 → 2026-10 · the evidence system",
    verses: [
      "Evidence comes in five grades. Java source diff. Static analysis. Contract check. Probe differential. And one that alone is called iron: base_pass_head_fail.",
      "Iron means this: the baseline's tests all passed, the head version's failed — one positive, one negative, on the same machine, beyond dispute.",
      "The Review Court is a night hearing: both sides present, and a deterministic policy hands down the penalty. Facts judge, not eloquence.",
    ],
    details: [
      { label: "Golden case", value: "the head-v1 demo removes @PreAuthorize from UserController.java — the most honest regression one can inject" },
      { label: "Probe anti-forgery", value: "9 counterexample locks, severity re-pinned (#1654); a false finding never enters the ledger (#1638)" },
      { label: "Execution surface disclosed", value: "execution_surface rides on every finding — where the evidence was obtained is always stated" },
    ],
  },
  {
    num: "Scroll 2",
    title: "Two Ends · The Vanguard and the Quartermaster",
    en: "The Twin Vanguards",
    era: "2026-10 → 2026-11 · front and back in step",
    verses: [
      "The Officer at the table needs two things: the file, and the witness. The front end is the scribe who hands him the file.",
      "So the scribe learned to speak in strokes: SSE progress, the stage timeline, the AI reading arriving one character at a time, a Markdown digest that drops straight into a review thread.",
      "Even the printout has standards: every page must deserve the word 'evidence' — margins, clauses, a seal, nothing missing.",
    ],
    details: [
      { label: "Stage timeline", value: "each stage placed on a time axis; stages without a timestamp are listed honestly below — never positioned by invention (StageTimeline, 5 test legs)" },
      { label: "Incremental AI reading", value: "SSE delivers character by character and replays from cache; a broken stream keeps what arrived and says so plainly (#1665)" },
      { label: "Copy to share", value: "'Copy Markdown summary' puts one verification's evidence into any review thread (#1664)" },
    ],
  },
  {
    num: "Scroll 3",
    title: "Compute · The War Over the Cache",
    en: "The Cache Doctrine",
    era: "2026-11 · the temple of metering",
    verses: [
      "Compute is a tide. At full tide it costs ten times; at low tide it scatters into drops. The clever do not dam the tide; they teach every drop the direction of the last one.",
      "So the founding discipline took shape: stable prefix first, variable tail last. A prompt is not prose — it is a cache key.",
      "Both lanes speak the same dialect now — stream=True + include_usage — so cache hits finally reach the ledger, and tokens stop leaving in silence.",
    ],
    details: [
      { label: "Streaming unified", value: "legacy lane #1644, policy lane #1663 — the gateway dashboard has not shown 'non-stream' since" },
      { label: "Billing basis", value: "cached_tokens → prompt_cache_hit_tokens → 0.1× weight in the ledger (#1644)" },
      { label: "Measured live", value: "_JUNIT_GENERATION_PROMPT prefix, 2272 bytes: 42.1s → 9.1s, 96.5% hit (#1645, measured)" },
      { label: "A/B recorded", value: "#1668 — two datasets side by side; the gateway owns its cache, we only record" },
    ],
  },
  {
    num: "Scroll 4",
    title: "The Battalions · A Steel Rampart Rises",
    en: "The Steel Rampart",
    era: "2026-11 · microservices",
    verses: [
      "One soldier does not make an army. The Officer needs each in its post: the edge as gate, the register as roster, the codebook as archive, the breaker as wall.",
      "Eureka puts a name on every instance — specproof-gateway. The config server keeps every setting in one book. The gate honours exactly one route table, and the isomorphism gate guards it.",
      "The breaker is a portcullis: when the far side dies, the gate closes instead of stalling; when it has not failed enough, it does not accuse.",
    ],
    details: [
      { label: "Eureka registration", value: "discovery-server on 8769, register-with-eureka — the edge lists itself in the roster (2026-11-14, #1674)" },
      { label: "Edge breaker", value: "12 calls against a dead upstream: state closed → open at the fifth, 503 instead of a hang (#1674)" },
      { label: "Config refresh", value: "POST /actuator/refresh → witness meter specproof_edge_config_refresh_events_total 0.0 → 1.0 (#1673/#1674)" },
      { label: "Health discipline", value: "RabbitMQ is an opt-in bus — its absence must not turn /health red, exactly like Redis (#1674)" },
    ],
  },
  {
    num: "Scroll 5",
    title: "The Chronicler · One Book, Nothing Erased",
    en: "The Chronicler's Ledger",
    era: "throughout · the discipline of governance",
    verses: [
      "The chronicler does two things only: write down what happened, and never erase what was written.",
      "Every 'done' has a ledger line you can audit: the command, the output, the date, the truth. The ledger does not gild a face, and does not hunt for excuses.",
      "As for the urge to prove it to yourself — that gets written down too. Probe A buried a disclosure in the merge layer: nine tests went red. Probe B reverted the fix: four went red. **The locks are real, not decorative.**",
    ],
    details: [
      { label: "Append-only ledger", value: "docs/operations/DEEP_OPTIMIZATION_PLAN.md — #1620 → #1674, each entry carrying the command, the output and the date" },
      { label: "Four gates on the ledger", value: "IDs unique · numbering unique · queue pointers resolve · evidence claims are true" },
      { label: "Red lights kept", value: "the failing counts are recorded, not hidden — a red light is this town's manners" },
    ],
  },
  {
    num: "Scroll 6",
    title: "The Unfinished Road",
    en: "The Unfinished Road",
    era: "2026-11 · today",
    verses: [
      "An IOU is not a shame — it is a map; every blank on it carries a name.",
      "The showcase tells no lies. Sundays 06:00 UTC, the vitrine inches forward.",
      "The keeper writes the unfinished on the wall — the full test suite has not run green here, and nobody may paint over that.",
    ],
    details: [
      { label: "The unfinished map", value: "World book Vol.XV landed (#1727): six open plots, each with its 'what done looks like' — the final word finally has a next page" },
      { label: "The showcase deal", value: "portfolio-sync ships data/specproof-* weekly (#1722); without PORTFOLIO_TOKEN it rebuilds and never pushes" },
      { label: "The truth about the meter", value: "wkapi's '96.5% hit rate' was the gateway's 4224-token constant — downgraded to an observational metric (#1723); provider_smoke really ran, 7/7 PASS (#1724)" },
      { label: "The foundation check", value: "demo doctor: six static checks, an honest WARN on a dirty demo tree (#1728); ghost routes in the guide cleared and held by a gate (#1726)" },
    ],
  },
  {
    num: "Scroll 7",
    title: "The Twelve Iron Scales",
    en: "The Twelve Iron Scales",
    era: "2026-11 · today",
    verses: [
      "When a tongue has two colours, evidence has one — press the button, the tone is the truth.",
      "A missed question is never the end; the re-forge review is where the craft is actually learned.",
      "From “it claims to be bilingual” to “the toggle switches it” lies 147 keys and one repair that deleted no test.",
    ],
    details: [
      { label: "147 keys", value: "toneMap/errorHints (#1730) + stages/preflight (#1732) — glosses resolve per locale; i18n parity locks both tables in both directions" },
      { label: "The twelve scales", value: "#/drill, Verify Drill (#1733): 12 questions anchored to the real declared domains and ledgers; four seals; 497/497 vitest green" },
      { label: "Baseline red → real green", value: "verdict_channel_parity was red on master itself — api/ai_summary.py declared as a job_summary carrier (owner + opaque); green for real (#1730)" },
      { label: "Ghost routes cleared", value: "/mcp, /admin/identity, /readme removed from both guides; the route-catalog gate stands guard (#1726); the key-inversion incident (#1732) written verbatim into the book" },
    ],
  },
  {
    num: "Scroll 8",
    title: "The Two-Tongued Verdict",
    en: "The Two-Tongued Verdict",
    era: "2026-11 · today",
    verses: [
      "Speak to the user in two languages; speak to the machine in two languages; speak to the ledger only in the truth.",
      "Caching is never a promise — it flips its flag at will; a red light is not a mood — it is a colour.",
      "The gate checks the tags before it trusts you; a promise gets a lock before a merge.",
    ],
    details: [
      { label: "Same sentence, same verdict", value: "#1741: gpt-6-sol zh→BLOCKER (4749 tokens, cached 3981); en→BLOCKER (4727 tokens, cached None); CONSISTENT — bilingual UI is not an imagined double promise" },
      { label: "The probe is not a gate", value: "divergence would only land in the ledger as DIVERGENT — observation, never verdict (#1723's discipline)" },
      { label: "CI guards the manual's promises", value: "#1740: .github/workflows/demo-doctor.yml; master push/PR; fetch-depth:0 keeps base/head-v1 tags — a shallow clone would hollow this gate into an alarm" },
      { label: "A living exhibit of the cache", value: "same probe run, zh cached=3981 vs en cached=null — #1723 holds: the hit rate is a surface, never a contract" },
    ],
  },
  {
    num: "Scroll 9",
    title: "The Forge and the River",
    en: "The Forge and the River",
    era: "2026-11 · today",
    verses: [
      "A forge does not do the work for you — it only guarantees that everything you carry away from it is real iron.",
      "A screen cannot replace a machine; its only virtue is putting five things on the same table: light, iron, fire, failure and truth.",
      "The river's true name is the state machine — every drop in is a state, every drop out is evidence.",
    ],
    details: [
      { label: "The forge #/ide (#1757)", value: "six real anchors + five runnable spells + a forge journal (localStorage); there is no cloud IDE — FastAPI serves the SPA and calls it a day" },
      { label: "The river #/graph (#1758)", value: "agent/graph.py::build_phase0_graph(), eighteen nodes and two guard rails, drawn verbatim — the browser never runs Python" },
      { label: "RAG that was really run (#1757)", value: "scripts/repo_rag.py — pure-Python TF-IDF, 142 markdown files, top-5 fed to wkapi/gpt-6-sol; ask caching is not contract and get cited back to POCKET_CARD" },
      { label: "/health 59 seconds, halved (#1755)", value: "MySQL + Redis probes ran serially: 29.18 s on dead backend; parallelized: ~27 s — marginal, honest, not sellable" },
    ],
  },
  {
    num: "Scroll 11",
    title: "The Chronicle",
    en: "The Chronicle",
    era: "2026-11 · today",
    verses: [
      "The keeper wakes before dawn to check whether the teapot is full — because what was unfinished is not a scroll, it is a task.",
      "A chronicle is always unfinished: whoever merges a PR owes the book a complete re-read; nobody earns it by being too lazy to rerun.",
      "No keeper dares say “the ledger is in charge.” The ledger only says what it knows; it cannot announce that it is done.",
    ],
    details: [
      { label: "build_chronicle.py (#1761)", value: "pure stdlib: parses the `## #NNNN` headings out of DEEP_OPTIMIZATION_PLAN.md plus the first meaningful sentence; writes apps/web/src/pages/chronicle.json — 1,561 entries, #130 → #1760" },
      { label: "chronicle.json (#1760)", value: "≈260 KB, one row per entry — number, title, first meaningful sentence; starts at #130 (the keeper does not write for themselves)" },
      { label: "Chronicle page #/chronicle (#1760)", value: "vertical-ink timeline, searchable across title/body/#NNNNN — honest by construction; merge an entry and the page lies the moment you stop paying attention" },
      { label: "The keeper's two laws (Vol. XIX)", value: "Either it did X or it did not X — nothing else; the chronicle is not a perpetual machine: changing the ledger obliges a re-run of build_chronicle.py" },
    ],
  },
  {
    num: "Scroll 12",
    title: "The Pocket Manual",
    en: "The Pocket Manual",
    era: "2026-11 · today",
    verses: [
      "A sleeve does not hold a sword; it holds one folded page — the page that says what you must know before the door opens.",
      "If evidence does not precede decision, decisions precede evidence, but the pocket manual precedes both: it is the preamble to the threshold.",
      "The card is not a tutorial — it is a permanent small reminder that you came, you read, you did not forget.",
    ],
    details: [
      { label: "The Manual page #/manual (#1766)", value: "SPECROOF POCKET CARD inside the app — A4 printable paper, gold hairline, bilingual; print and go" },
      { label: "The Triad (since #72, #1702)", value: "#/guide (ordered path) + #/tour (six stamps) + #/manual (one page) — not alternatives, but three verses of the same poem" },
      { label: "A card, not a slide deck", value: "five things on the way in + three do-nots + five repo commands — read once, keep it close, never taught again" },
      { label: "The secret of the card", value: "it always folds into the pocket; it always knows which page you stopped reading yesterday" },
    ],
  },
  {
    num: "Scroll 13",
    title: "The Evidence Archipelago",
    en: "The Evidence Archipelago",
    era: "2026-11 · today",
    verses: [
      "A world that never ends does not owe you lostness — the first chart drawn for you is the archipelago's whole hospitality.",
      "Three islands on one map: the Workspace Highlands, the Evidence Plains, the Governance Coast — twenty-four halls in their rightful seats.",
      "The scale bar ticks real commits — 0, 1,000, 2,000, 2,400+ — the chart cannot lie because it stands on git.",
    ],
    details: [
      { label: "The Atlas, #/atlas (#1770)", value: "SPECROOF ATLAS — three islands x 24 halls + three expedition routes + living landmarks (all git ls-files-derived)" },
      { label: "Inspected in-frame (#1771)", value: "bbox math QA: islands inside the frame, N inside the dial, caption inside the margin — no ornament crosses the gold rule" },
      { label: "Three expedition routes", value: "Fast Shore 90s (tour→manual) · Evidence Expedition 25min (epic→chronicle→census) · Live-Fire 10min (jobs/new→matrix→FindingDetail)" },
      { label: "A map is not a substitute for exploration", value: "It is the porch over the threshold — the one who reads it dares the plains; what cannot be drawn is sand, not land" },
    ],
  },
  {
    num: "Scroll 14",
    title: "The Reading Room",
    en: "The Reading Room",
    era: "2026-11 · today",
    verses: [
      "A book worth keeping for life should not sleep in a terminal — the official history deserves a room, and the room deserves pages and a bookplate.",
      "Twenty-nine sections shelved verbatim: frontispiece, Volumes 0–XXII, appendices A–D, the final chapter — every glyph checkable against the repo.",
      "Every volume you finish in the reading room is your territory; the ones you have not read are waiting behind their doors.",
    ],
    details: [
      { label: "The Reading Room, #/worldbook (#1774)", value: "29 sections (frontispiece + 23 volumes + 4 appendices + final chapter), bilingual · full-text <mark> search · local reading progress · random-volume draw" },
      { label: "One quarry of raw material", value: "docs/world/SPECROOF_WORLD.md (zh) + EN/SPECROOF_WORLD_EN.md (en) — build_worldbook.py shelves them verbatim" },
      { label: "A reading room, not a showroom", value: "marked renders tables/code/quotes; two hits in the current volume light up instantly; one stamp per finished volume" },
      { label: "The room ages", value: "every master merge re-runs scripts/build_worldbook.py — the room lights up at the pace of the book" },
    ],
  },
  {
    num: "Scroll 15",
    title: "The IOU Epigraph",
    en: "The IOU Epigraph",
    era: "2026-11 · today",
    verses: [
      "An IOU is not a shame — it is a map; every blank in it carries a name and a ledger number.",
      "On 2026-11-16 the owner wrote one line by hand: 'do them all, I approve everything.' §9 of OBSERVABILITY.md now carries the signature; the D2 twin (PORTFOLIO_TOKEN) is still owed.",
      "The iron does not blink: exhibit #4 stays on file forever, and tonight the composite watch reads CRACKED — nobody asked it to be jade.",
    ],
    details: [
      { label: "D1 signed · OBSERVABILITY.md", value: "owner-authorised (#1897); signature block found; identity NOT crypto-verified — recorded as such, never as verified" },
      { label: "D2 still owed", value: "PORTFOLIO_TOKEN lives in your own Settings→Secrets; nobody mints it here. Sundays 06:00 UTC the workflow knocks: products.json · latest.md · .github-sync.json — silent until you decree" },
      { label: "The red of the watch", value: "exhibit #4 (1,526.1 ms) and exhibit #8 (2,078.7 ms) hang on /engine forever; the Δ>25 ms rule never moved (#1890); exhibit #9 (64c · p99 1,596.9 ms · #1912) pinned today" },
      { label: "R14's postmark", value: "without the ladder every probe came back region-blocked; through Clash Verge (7897) the lane answered (#1884): HTTP 200 · 9 chunks · cached 4224→6400" },
    ],
  },
  {
    num: "Scroll 16",
    title: "The Screen That Speaks One Language",
    en: "The Screen That Speaks One Language",
    era: "2026-11 · today",
    verses: [
      "A screen that speaks two languages is not bilingual — it is noise. Chinese mode is all Chinese; English mode is all English.",
      "Graphs are not decoration; they are the contract. Eight run live here — every verdict fail-closed; Night Watch stays CRACKED.",
      "Every page in this book is knockable: /errata keeps the sixteen corrections; /stategraph is the eight words with the eight living graphs.",
    ],
    details: [
      { label: "The purity gate · i18n.purity.test.ts", value: "zero CJK / punctuation / fullwidth in en; zero English link-word runs in zh — shipped with vitest (#1909)" },
      { label: "/errata — the corrections wall", value: "R01–R15 · bilingual · searchable · each anchored to a commit; a query exposes, never erases (#1908)" },
      { label: "/stategraph — the eight words", value: "the state-machine field guide + recall/evidence/purity/auditor/night_watch, plus the night-watch verdict verbatim — CRACKED never painted jade (#1910)" },
      { label: "The overflow guard", value: "anywhere-wrap headings, media max-width, pre overflow-x — hidden nothing, only scroll (#1911)" },
      { label: "The two shadows · 8888", value: "the control-plane's prometheus/refresh lights were shadowed by the stale 8888 server; the exposure pin fixed it (#1912); mvn -o 137/137 re-struck GREEN" },
      { label: "The sixth graph · /stategraph", value: "cache_witness_graph lands: the same fixed prompt struck twice · cached_tokens=4224×2 · hit_rate 95.3% · HIT — the only graph in this book that phones the model lane, on purpose; /stategraph now carries six living graphs (#1933)" },
      { label: "Insight AI Advice · /insight", value: "the Insight Deck gained \"AI Advice — what the data says next\": admin/operator asks aizzz/gpt-6.1-terra to read this panel\'s anonymous aggregates — allowlisted packet (zero PII) · first strike 730 B · latency 17,032 ms · model quoted 201→113 / 84→41 verbatim · volunteered \"insufficient data\" on onboarding_routes=0; RBAC untouched (#1936)" },
      { label: "The model wrote the patch · craft×aizzz", value: "a free-form Chinese requirement (\"fix the logic error in double\") → plan.mode=llm · four Chinese steps · the model itself edited x / 2 → x * 2 (no fix_registry) → LOOP_RESULT=DONE → **acceptance BLOCKED** (this host's Docker python cache carries no pytest · No module named pytest — the door never moved, the patch was rolled back, the world returned to base) · cached 4224 struck on the second call (#1937)" },
      { label: "The sandbox bites pytest · #1938", value: "the three-phase composite is on file: venv → offline wheelhouse install (pytest 9.2.0 seeded) → pytest (rewritten in effective docker mode only; local mode byte-identical) · 25/25 runner assertions · **run_test green for the first time** (155 s · exit 0) · Docker Desktop died once on the spot (unexpected EOF), recorded as-is; SpecProof REJECTED (Java/Maven-first · No pom.xml) — the wall got named, never smoothed (#1938)" },
      { label: "The delta against the earliest one · #1939", value: "exhibit #14 (2026-11-16T17:48Z · 48c ×2×4) on file: err 0.00% · worst p99 1,074.4 ms · OK; re-struck against exhibit #2 (2026-11-15T17:28Z): Δp99 −462.9 ms · p50 drifted up ~2.5× — recorded as-is, never spun; exhibit_entries 14 → 15 (#1939)" },
      { label: "The 384 rung · #1940", value: "exhibit #15 (2026-11-16T17:56Z · 384c ×2×4 rounds + 3 warmup) on file: rounds err 4.43/2.34/4.30/4.04% · p50 ~530–547 ms · worst p99 2,061.0 ms · BUDGET-BLOWN — 192→256→384 tonight is non-monotone (64–70% → 34–45% → 2–4%) · the saturation curve gained the 384c tick; exhibit_entries 15 → 16 (#1940)" },
      { label: "The seventh graph · #1942", value: "insight_advice_graph.py lands: intake → strike → verdict → report → END — watches the Insight Deck model lane; ANSWERED is its only utterance; struck live: ANSWERED · latency 46,519 ms · cached 0 (a different prefix) — the seven living graphs (5 offline + 2 networked) on /stategraph (#1942)" },
      { label: "Three red doors open · #1945", value: "the design-system #8 roster cracked: 4px grid 601→0 · font scale 406→0 · radii 101→0 · shadows 71→0 · 1,165 theme-blind literal colours left on file (untouched; needs semantic naming — a remediation batch of its own) · Night Watch CRACKED · exhibit_entries=16 (#1945)" },
      { label: "The door that does not fall · #1944", value: "rate-limit cemented: SPECPROOF_RATE_LIMIT_PER_MIN default 5/min · specproof:rl:<sha256(key)[:16]>:<window> · incr→count==1 expire(90) · count>limit ⇒ 429 RATE_LIMITED · fail-open is a rule, not a bug · 32 consecutive wrong keys → all 401 · tests/unit/test_rate_limit_fixed_window.py 3/3 (#1944)" },
      { label: "The red door, half foot more · #1946", value: "theme-blind colours 1,165 → 593: sweeping gates station by station through pytest · glow/brass/parchment/steel named · tokens.css drifted twice then the double-pass rule landed · exhibit_entries=16 (#1946)" },
      { label: "Every door is open · #1947", value: "theme-blind colours 593 → **0**: 463 `--pigment-*` tokens registered byte-for-byte · 13 re-binds to context-invariant tokens (never the `--print-*` lane) · the entire design-system family is green on master (grid/radii/scale/shadow/colours all 0) (#1947)" },
      { label: "One ledger, two measures · #1948", value: "the cache account split along lane × protocol (by_lane: direct **0.5418** / policy **0.0** with machine backing for R16) · Usage panel gains the twin tables · +3 honesty tests (20/20) (#1948)" },
      { label: "The coarse measure, made honest · #1949", value: "i18n audit upgraded: bucket A **366→196→138** · bucket C added (`L()`/`zh ?`/`{ zh: }`/`…_ZH` same-line coordinated bilinguals — 1,172 reclassified) · noise down, nothing blessed, audit stays exit 0 forever (#1949)" },
      { label: "The eighth graph · #1950", value: "usage_ledger_graph.py lands: intake → strike → verdict → report → END — read the local token ledger with the Usage panel's own accounting; live strike: ANSWERED · window 24h · 38 calls · 6 errors · hit_rate 0.430 (basis 32) · the eight living graphs (6 offline + 2 networked) on /stategraph · ANSWERED/UNAVAILABLE reuse the witness lexicon (#1950)" },
      { label: "The ninth graph · #1954", value: "investigation_dig_graph.py lands: explorer / tester / security fan out in parallel on one question — struck live against aizzz/gpt-6.1-terra · verdict EVIDENCE-GATHERED · /stategraph now hangs nine living graphs (six offline + three networked) · StateGraph.test.tsx 8/8 (#1954)" },
      { label: "The Dig · #1955", value: "/api/v1/admin/investigation-dig + /dig page — the same three readonly investigators ask this repo a question (fact pack bounded ≤4 KB); struck live against aizzz/gpt-6.1-terra · verdict EVIDENCE-GATHERED · 16,200 tokens accounted in the ledger · UI 576/576 (#1955)" },
      { label: "The bookkeeper signs for itself · #1957", value: "witness channel re-registered for the dig surfaces: owners 19→23 · opaque 19→23 · witness pointer craft/investigators.py:294 · parity back to 14/14 (#1957)" },
      { label: "Every red door struck again · #1958", value: "the full door audit: 26 reds → 24 (23 payload-census stay in item #8, one U+FFFD at the ledger stays on file — the byte is unrecoverable and no fake was written in) · mypy 289/289 · mvn -o both services BUILD SUCCESS · every surface kept in step (guides · RBAC · the direct-LAN target got its SpecproofLocalHostApiDown probe · FAKE_INVENTORY pin → b7a011a · the two demo-marker gates follow the copy pack) (#1958)" },
      { label: "The runbook answers · #1959", value: "runbook_triage_graph.py / /api/v1/admin/runbook-triage + /runbook page — the alert fires, the model reads the repo (one alerts-slo rule × last 20 commits × five newest evidence files × the redacted api env) · verdict CONFIRMED / INCONCLUSIVE · /stategraph hangs its tenth living graph · UI 580/580 (#1959)" },
      { label: "The terms explain themselves · #1960", value: "glossary gains three Runbook entries — `dig` (深挖现场), `runbook` (值班手册), `inconclusive` (证据不足) — wrapping <Term id=…> directly on the page, single source of truth, never copied definitions · UI 580/580 (#1960)" },
      { label: "The Observatory · #1966", value: "/observe is a public, read-only, demo-only page: the 240-member synthetic calibration cohort + this browser's real taps · r² / slope / funnel bilingual · password \"123\" opens a live model read (server-side lane · fingerprint-cached) — never any real person's data · UI **587/587** (#1966)" },
      { label: "One Real Machine · #1967", value: "/observe adds \"This one machine\": this browser's true climate from `specproof_heat_v1` (taps · bounces · rage · dwell median) · never uploaded · silence is not zero · the model lane still reads only the anonymous aggregates · UI **589/589** (#1967)" },
      { label: "The Unmixed Chapter · #1968", value: "i18n hybrid strike-down — zh branches grow no English tails · bucket A 37→29 · UI **589/589** (#1968)" },
      { label: "The Covenant · #1969", value: "`api/system_covenant.py` — byte-identical Chinese charter (11 laws · pinned to repo-truth files) carried by five cacheable lanes; court never carries it; provider cache honoured honestly as-is · UI **589/589** (#1969)" },
      { label: "Live Numbers · #1970", value: "Archive takes live values everywhere: World Book **171** · Inkwell **2,643** (span 130 d · streak 16) · dossier **111** · inkwell.json re-struck · UI **589/589** (#1970)" },
      { label: "The Covenant Witness · #1971", value: "StateGraph lamp #11 — covenant pinned byte-for-byte to its #1969 day · never strikes a model · parity **14/14** · UI **590/590** (#1971)" },
      { label: "Its Own Evidence · #1972", value: "the full 32-red bench reconciled name by name · five red gates fixed on the spot (parity · 4px grid · D08 knob ledger · fake-inventory pin · client-closure roster) · payload-census pin confirmed at 22 · UI **590/590** (#1972)" },
    ],
  },
  {
    num: "Scroll XVII",
    title: "The Night Watch Inside the Badge",
    en: "The Night Watch Inside the Badge",
    era: "2026-11 · today",
    verses: [
      "When no one knocks, the watch does not stop — exhibit #4 stays pinned; the verdict stays CRACKED.",
      "The gateway said “cache hit” once (4224) — the keeper recorded it, and recorded the two 0/0s after it. The one who says “improved” is never the keeper.",
      "The night is quiet, not because it was guarded, but because the watcher never once closed their eyes.",
    ],
    details: [
      { label: "exhibit #9 · 64c", value: "512 req · err 0.00% · worst p99 1,596.9 ms — the gap between #7 (48c) and #8 (96c) struck shut; Night Watch remains CRACKED (#1912)" },
      { label: "The two shadows · 8888", value: "two actuator tests in control-plane 404'd (prometheus/refresh swallowed by the host's stale 8888 config-server) → exposure pin in both test profiles; mvn -o 137/137 re-struck GREEN (#1912)" },
      { label: "R16 · The Sixteenth R", value: "two_strike_probe.py (scripts/) — same prompt twice, prompt_cache_hit_tokens = 0 / 0; R16 filed: one cached≠cache improvement (corrections 16 — #1915)" },
      { label: "README re-drawn to truth", value: "stale model tables (ynynzyy·gpt-6-astra · wkapi.pro·gpt-6-sol) replaced by api.aizzz.xyz/v1 · gpt-6.1-terra · responses · stream+include_usage · max — Clash Verge 127.0.0.1:7897; R14 noted (#1916)" },
      { label: "The gate cleared", value: "routerSmoke: 43 NAV destinations × both locales mount; render-crash boundary断言; deliberate /graph bomb → two red locale runs pinned to #/graph; revert → green; UI 559/559 (#1914)" },
    ],
  },
];

export const SCROLLS_BY_LOCALE: Record<Locale, Scroll[]> = {
  zh: SCROLLS_ZH,
  en: SCROLLS_EN,
};

export const CLOSING_EN = [
  "Coda · Unfinished",
  "Every victory, every defeat, every ledger line and every scroll of this book lands on one answer: the iron verifies itself.",
  "The roadmap (PRODUCT_ROADMAP.md) still lists what is open: 1.3 demo self-check, 1.6 verify kernel decoupling, 4.2 counterexample policy, 5.3 observability default-on, 5.4 deployment shape, 6.1 IDE/CI integration — every one of them is written down, waiting for the next commit.",
];

export const CLOSING_BY_LOCALE: Record<Locale, string[]> = {
  zh: CLOSING_ZH,
  en: CLOSING_EN,
};

export interface PrologueSegment {
  /** When true the segment renders inside a <strong> (the book's iron words). */
  b?: boolean;
  text: string;
}

/**
 * The frontispiece paragraph. The Chinese text is the original; the English is
 * its faithful translation (not a paraphrase — every claim maps one-to-one).
 * Both render with the same three <strong> pins.
 */
export const PROLOGUE_BY_LOCALE: Record<Locale, PrologueSegment[]> = {
  zh: [
    { text: "此书始于一个简单的问题：" },
    { b: true, text: "AI 写的代码，谁配说「过了」？" },
    { text: "答案不是模型的自信、也不是评审的好运气，而是" },
    { b: true, text: "一炉可复现的铁证" },
    { text: "：契约编译成法律、差分执行成证言、矩阵列出罪名，再由确定性策略定谳。SpecProof 不是一个「检查代码的工具」，它是一台为每个变更验明来路的" },
    { b: true, text: "验收机器" },
    { text: "。" },
  ],
  en: [
    { text: "This book started with one simple question: " },
    { b: true, text: "who may say “passed” about AI-written code? " },
    { text: "Not the model’s confidence. Not the reviewer’s luck — a furnace of " },
    { b: true, text: "reproducible iron evidence" },
    { text: ": contracts compiled into law, differential runs turned into testimony, the matrix listing the charges, and a deterministic policy hands down the verdict. SpecProof is not a “code-checking tool” — it is the " },
    { b: true, text: "acceptance machine" },
    { text: " that verifies the origin of every single change." },
  ],
};

export const PROLOGUE_MARK_BY_LOCALE: Record<Locale, string> = { zh: "始", en: "P" };
