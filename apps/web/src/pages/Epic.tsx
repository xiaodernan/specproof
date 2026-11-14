import "../styles/verification.css";

// 史诗 · The Chronicles of SpecProof —— 给一切验收动作一个起源与一个收束。
// 本页所有数字、提交号、账本条目标号全部是本项目真实发生过的事，
// 每一章底部的「史官细则」都能在 docs/operations/DEEP_OPTIMIZATION_PLAN.md 与 git log 中找到对应条目。
// 凡本项目尚未完成的事，一律写为"未完"而不是"已成"。

interface ScrollDetail {
  label: string;
  value: string;
}

interface Scroll {
  num: string;
  title: string;
  en: string;
  era: string;
  verses: string[];
  details: ScrollDetail[];
}

const SCROLLS: Scroll[] = [
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

const closing = [
  "尾声 · 未完",
  "史官的本子翻到这页，只道一件事：没写完。路线图还有项未静声：1.3 演示自检、1.6 Verify 解耦、4.2 反例裁决、5.3 可观测开箱、5.4 部署形态、6.1 IDE/CI 集成——每一笔都写着下一步的名字。",
  "铁证不因多而更硬，也不因少而失重。验收官若问「我能信它吗」，答案永远不在卷首，而在卷末：铁证，自证。",
];

export default function Epic() {
  return (
    <div className="chronicles-page">
      <div className="page-head">
        <h1>史诗 <span className="chronicles-en">The Chronicles of SpecProof</span></h1>
        <div className="page-sub" title="THE LEDGER AND THE LEGEND">
          一部关于「验收」的史书——为 AI 写下的每一行代码验明来路、坐实铁证、定谳如山。本页每一卷都对应本项目仓库中的真实实录；翻到哪一卷，都该能在 git 历史和账本里找到同一件事。
        </div>
      </div>

      <div className="chronicles-prologue">
        <span className="chronicles-prologue-mark" aria-hidden="true">序</span>
        <p>
          此书始于一个简单的问题：<strong>AI 写的代码，谁配说「过了」？</strong>答案不是模型的自信、也不是评审的好运气，而是<strong>一炉可复现的铁证</strong>：契约编译成法律、差分执行成证言、矩阵列出罪名，再由确定性策略定谳。SpecProof 不是一个「检查代码的工具」，它是一台为每个变更验明来路的<strong>验收机器</strong>。
        </p>
      </div>

      {SCROLLS.map((scroll) => (
        <article className="chronicles-scroll" key={scroll.num} id={"scroll-" + scroll.num.replace(/[^0-9a-zA-Z]/g, "")}>
          <div className="chronicles-spine" aria-hidden="true"><span>{scroll.num.slice(1)}</span></div>
          <div className="chronicles-body">
            <header className="chronicles-scroll-head">
              <span className="chronicles-seal">{scroll.num.slice(1)}</span>
              <div>
                <h2>{scroll.title}</h2>
                <div className="chronicles-en">{scroll.en} · {scroll.era}</div>
              </div>
            </header>
            {scroll.verses.map((v, i) => (
              <p className="chronicles-verse" key={i}>{v}</p>
            ))}
            <div className="chronicles-details">
              <div className="chronicles-details-title">史官细则 · 可核验</div>
              <dl>
                {scroll.details.map((d) => (
                  <div className="chronicles-detail-row" key={d.label}>
                    <dt>{d.label}</dt>
                    <dd>{d.value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </div>
        </article>
      ))}

      <div className="chronicles-closing">
        <span className="chronicles-prologue-mark" aria-hidden="true">尾</span>
        <div>
          <h3>{closing[0]}</h3>
          <p>{closing[1]}</p>
          <p>{closing[2]}</p>
        </div>
      </div>

      <p className="chronicles-colophon muted">
        本页由史官（也就是这个仓库里的每一次提交）立下：2026-09 → 今。账本在 <code>docs/operations/DEEP_OPTIMIZATION_PLAN.md</code>，
        路线图在 <code>docs/operations/PRODUCT_ROADMAP.md</code>；铁证不因多而更硬，也不因少而失重。
      </p>
    </div>
  );
}
