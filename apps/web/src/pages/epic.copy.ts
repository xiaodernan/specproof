import type { Locale } from "../i18n/strings";

/**
 * The English edition of the Epic page's six scrolls.
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
