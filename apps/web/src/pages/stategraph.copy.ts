import type { Locale } from "../i18n/strings";
import nightWatch from "./night_watch.json";
import cacheWitness from "./cache_witness.json";
import adviceWitness from "./insight_advice_witness.json";
import usageLedger from "./usage_ledger_witness.json";
import investigationDig from "./investigation_dig.json";
import runbookTriage from "./runbook_triage.json";
import covenantWitness from "./covenant_witness.json";
import exhibitCopilot from "./exhibit_copilot.json";

/**
 * 状态图谱 · The State Graphs — everything this page says is either
 * copied verbatim from the fifteen graphs in `agent/graphs/`, or is a concept
 * note about LangGraph's StateGraph as used by this repository.
 *
 * No LLM writes anything here; no network is involved; the browser re-draws
 * committed JSON at render time and nothing else.
 */

export interface Concept {
  id: string;
  term: Record<Locale, string>;
  gloss: Record<Locale, string>;
}

export const CONCEPTS: Concept[] = [
  {
    id: "state",
    term: { zh: "State 状态", en: "State" },
    gloss: {
      zh: "一个 TypedDict，total=False ——节点只回它改变了的字段；没人填全表。这本项目所有图都从这种「只填增量」的状态开始。",
      en: "A TypedDict, total=False — each node returns only the fields it changed; nothing fills the whole table. Every graph in this book starts from this delta-filling posture.",
    },
  },
  {
    id: "node",
    term: { zh: "Node 节点", en: "Node" },
    gloss: {
      zh: "一个纯函数 def node(state) -> 部分 state。没有副作用、没有网络、没有隐藏全局——这就是这个仓库的节点长相。",
      en: "A pure function def node(state) -> partial state. No side effects, no network, no hidden globals — that is what a node looks like in this repository.",
    },
  },
  {
    id: "edge",
    term: { zh: "Edge 边", en: "Edge" },
    gloss: {
      zh: "固定边 add_edge(A, B)：从 A 必到 B。这个仓库里最常用的边就是 intake → 第一个真正工作的节点。",
      en: "Fixed edge add_edge(A, B): from A you always arrive at B. The most common edge in this repository is intake → first real worker.",
    },
  },
  {
    id: "conditional-edge",
    term: { zh: "Conditional Edge 条件边", en: "Conditional edge" },
    gloss: {
      zh: "add_conditional_edges(A, fn, {…})：边上带判断。phase0 图里 _abort_on_preflight→publish_report、_abort_on_errors→publish_report，就是短路判决：环境不行就整件事出炉。",
      en: "add_conditional_edges(A, fn, {…}): the edge carries a verdict. In the phase-0 graph, _abort_on_preflight→publish_report and _abort_on_errors→publish_report are the short-circuits: when the environment is impossible, the whole trial is over before it starts.",
    },
  },
  {
    id: "reducer",
    term: { zh: "Reducer / channel 通道", en: "Reducer / channel" },
    gloss: {
      zh: "LangGraph 的每个字段都是一条通道；append 是 reducer（比如 add_messages）。这本书的九个图全是 overwrite 通道——没有对话，不需要累积。",
      en: "Every field in LangGraph is a channel; append is a reducer (add_messages). All nine graphs in this book use overwrite channels — there is no dialogue to accumulate.",
    },
  },
  {
    id: "entry",
    term: { zh: "Entry point 入口", en: "Entry point" },
    gloss: {
      zh: "graph.set_entry_point(\"intake\") ——没有 set_entry_point 的图画得出来但跑不起来。九个图的入口全部是 intake / 第一个真相采集节点。",
      en: "graph.set_entry_point(\"intake\") — a graph without an entry point draws fine and runs never. All nine graphs enter at intake / the first truth-gathering node.",
    },
  },
  {
    id: "end",
    term: { zh: "END 终态哨兵", en: "END" },
    gloss: {
      zh: "哨兵 END 只做一件事：宣告这一轮结束。它不判断好坏——好坏看 verdict。八张图都以 END 收尾，这是 LangGraph 唯一的硬规则。",
      en: "The sentinel END does one thing: declare this round over. It passes no judgement — the verdict does that. All nine graphs end there; it is the one hard rule LangGraph gives you.",
    },
  },
  {
    id: "verdict",
    term: { zh: "Verdict fail-closed 判词", en: "Verdict (fail-closed)" },
    gloss: {
      zh: "这本书的图从不把「读不到」涂成绿灯——读不到就是 EVIDENCE-MISSING；exhibit #4 的 Δ>25ms 就是 REGRESSION；Night Watch 因为证据 REGRESSION 就 CRACKED。判词是 fail-closed 的：警报比遗漏更值钱。",
      en: "The graphs in this book never paint an unreadable thing jade — unreadable means EVIDENCE-MISSING; exhibit #4's Δ>25ms means REGRESSION; Night Watch says CRACKED because the evidence lane regressed. Verdicts are fail-closed: a false alarm is cheaper than a missed one.",
    },
  },
];

export interface GraphCard {
  id: string;
  file: string;
  stateName: string;
  chain: string[];
  verdicts: { zh: string; en: string };
  role: Record<Locale, string>;
  fields: string[];
  live: { zh: string; en: string } | null;
}

const NW = nightWatch as unknown as {
  verdict?: string;
  lanes?: { evidence?: string; purity?: string; audit?: string };
};
const CW = cacheWitness as unknown as {
  prompt_tokens_a?: number;
  cached_tokens_a?: number;
  prompt_tokens_b?: number;
  cached_tokens_b?: number;
  hit_rate_b?: number | null;
  verdict?: string;
};
const hitPct = ((CW.hit_rate_b ?? 0) * 100).toFixed(1);
const liveCacheWitness = {
  zh: `strike A cached=${CW.cached_tokens_a ?? "?"} · strike B cached=${CW.cached_tokens_b ?? "?"}（prompt ${CW.prompt_tokens_b ?? "?"}）· hit_rate ${hitPct}% → ${CW.verdict ?? "?"}`,
  en: `strike A cached=${CW.cached_tokens_a ?? "?"} · strike B cached=${CW.cached_tokens_b ?? "?"} on prompt ${CW.prompt_tokens_b ?? "?"} · hit_rate ${hitPct}% → ${CW.verdict ?? "?"}`,
};
const AW = adviceWitness as unknown as {
  packet_chars?: number;
  fingerprint?: string;
  model?: string;
  latency_ms?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  reasoning_tokens?: number;
  cached_tokens?: number;
  advice_chars?: number;
  verdict?: string;
};
const UL = usageLedger as unknown as {
  calls?: number;
  errors?: number;
  error_rate?: number | null;
  hit_rate?: number | null;
  hit_basis_calls?: number;
  streamed_ratio?: number | null;
  rows_read?: number;
  verdict?: string;
};
const liveInsightAdvice = {
  zh: `packet ${AW.packet_chars ?? "?"} B · fingerprint ${AW.fingerprint ?? "?"} · ${AW.model ?? "?"} · ${AW.latency_ms ?? "?"} ms · advice ${AW.advice_chars ?? "?"} 字 → ${AW.verdict ?? "?"}`,
  en: `packet ${AW.packet_chars ?? "?"} B · fingerprint ${AW.fingerprint ?? "?"} · ${AW.model ?? "?"} · ${AW.latency_ms ?? "?"} ms · advice ${AW.advice_chars ?? "?"} chars → ${AW.verdict ?? "?"}`,
};

const liveUsageLedger = {
  zh: `本窗 ${UL.calls ?? "?"} 次调用 · ${UL.errors ?? "?"} 次错误 · 流式占比 ${UL.streamed_ratio ?? "?"} · hit_rate ${typeof UL.hit_rate === "number" ? (UL.hit_rate * 100).toFixed(1) + "%" : "?"}（basis ${UL.hit_basis_calls ?? "?"}）· 门牌 ${UL.verdict ?? "?"}（全量行数 ${UL.rows_read ?? "?"})`,
  en: `${UL.calls ?? "?"} calls in the window · ${UL.errors ?? "?"} errors · streamed share ${UL.streamed_ratio ?? "?"} · hit_rate ${typeof UL.hit_rate === "number" ? (UL.hit_rate * 100).toFixed(1) + "%" : "?"} (basis ${UL.hit_basis_calls ?? "?"}) · verdict ${UL.verdict ?? "?"} (rows read ${UL.rows_read ?? "?"})`,
};
const ID = investigationDig as unknown as {
  verdict?: string;
  generation_time_ms?: number;
  total_tokens_used?: number;
  agents?: { name?: string; outcome?: string; tokens?: number; duration_ms?: number }[];
};
const liveInvestigationDig = {
  zh: `三位只读侦探 · ${(ID.agents || []).filter((a) => (a.name || "").includes("explorer") && a.outcome === "ok").length + (ID.agents || []).filter((a) => (a.name || "").includes("tester") && a.outcome === "ok").length + (ID.agents || []).filter((a) => (a.name || "").includes("security") && a.outcome === "ok").length}/3 到位 · 总计 ${ID.total_tokens_used ?? "?"} tokens · verdict ${ID.verdict ?? "?"}`,
  en: `three readonly investigators · ${(ID.agents || []).filter((a) => (a.name || "").includes("explorer") && a.outcome === "ok").length + (ID.agents || []).filter((a) => (a.name || "").includes("tester") && a.outcome === "ok").length + (ID.agents || []).filter((a) => (a.name || "").includes("security") && a.outcome === "ok").length}/3 landed · ${ID.total_tokens_used ?? "?"} tokens total · verdict ${ID.verdict ?? "?"}`,
};

const RT = runbookTriage as unknown as {
  verdict?: string;
  total_tokens_used?: number;
  generation_time_ms?: number;
  alert?: string;
  agents?: { name?: string; outcome?: string; tokens?: number; role?: string }[];
};
const liveRunbookTriage = {
  zh: `告警 ${RT.alert ?? "?"} · ${(RT.agents || []).filter((a) => a.outcome === "ok").length}/3 到位 · 总计 ${RT.total_tokens_used ?? "?"} tokens · verdict ${RT.verdict ?? "?"}（判词从裁判席上没人替它涂绿）`,
  en: `alert ${RT.alert ?? "?"} · ${(RT.agents || []).filter((a) => a.outcome === "ok").length}/3 landed · ${RT.total_tokens_used ?? "?"} tokens total · verdict ${RT.verdict ?? "?"} (nobody in court painted this jade)`,
};
const liveNightWatch = {
  zh: `evidence=${NW.lanes?.evidence ?? "?"} · purity=${NW.lanes?.purity ?? "?"} · audit=${NW.lanes?.audit ?? "?"} → ${NW.verdict ?? "?"}（exhibit #4 仍在册）`,
  en: `evidence=${NW.lanes?.evidence ?? "?"} · purity=${NW.lanes?.purity ?? "?"} · audit=${NW.lanes?.audit ?? "?"} → ${NW.verdict ?? "?"} (exhibit #4 still on file)`,
};

const CV = covenantWitness as unknown as {
  bytes?: number;
  sha256?: string;
  laws?: number;
  pinned?: boolean;
  verdict?: string;
};
const liveCovenantWitness = {
  zh: `行宪 ${CV.bytes ?? "?"} B · sha256 ${(CV.sha256 ?? "").slice(0, 12)}… · ${CV.laws ?? "?"}/11 法 · pinned=${CV.pinned} → ${CV.verdict ?? "?"}`,
  en: `covenant ${CV.bytes ?? "?"} B · sha256 ${(CV.sha256 ?? "").slice(0, 12)}… · ${CV.laws ?? "?"}/11 laws · pinned=${CV.pinned} → ${CV.verdict ?? "?"}`,
};

const EC = exhibitCopilot as unknown as {
  verdict?: string;
  pinned?: boolean;
  packet_ok?: boolean;
  reasoning_tokens?: number;
  cached_tokens?: number;
  prompt_tokens?: number;
};
const liveExhibitCopilot = {
  zh: `展厅铭 · prompt ${EC.prompt_tokens ?? "?"} tok · cached ${EC.cached_tokens ?? "?"} · 推理 ${EC.reasoning_tokens ?? "?"} · pinned=${EC.pinned} → ${EC.verdict ?? "?"}`,
  en: `exhibit wall · prompt ${EC.prompt_tokens ?? "?"} tok · cached ${EC.cached_tokens ?? "?"} · reasoning ${EC.reasoning_tokens ?? "?"} · pinned=${EC.pinned} → ${EC.verdict ?? "?"}`,
};

export const GRAPHS: GraphCard[] = [
  {
    id: "recall",
    file: "agent/graphs/recall_graph.py",
    stateName: "RecallState(TypedDict, total=False)",
    chain: ["intake", "search", "verdict", "END"],
    verdicts: { zh: "HIT / MISS / MISSING-QUERY / EVIDENCE-MISSING", en: "HIT / MISS / MISSING-QUERY / EVIDENCE-MISSING" },
    role: {
      zh: "问铁——把史官账本里的一个字眼敲进去，BM25 现场排序，不调用任何模型；问不到就 MISS。",
      en: "Ask the iron — strike a question at the keeper's ledger and get a BM25-ranked answer with no model in the loop; a miss is a MISS, not a paraphrase.",
    },
    fields: ["query", "docs_dir", "top", "hits", "verdict", "detail", "generated_utc"],
    live: null,
  },
  {
    id: "evidence",
    file: "agent/graphs/evidence_graph.py",
    stateName: "EvidenceState(TypedDict, total=False)",
    chain: ["intake", "collect_series", "verdict", "emit_report", "END"],
    verdicts: { zh: "OK / REGRESSION / EVIDENCE-MISSING / NO-DELTA（Δ>25ms）", en: "OK / REGRESSION / EVIDENCE-MISSING / NO-DELTA (Δ>25ms)" },
    role: {
      zh: "量骨——把 16 件展品逐个敲 p99；exhibit #4 一条 REGRESSION 就足以把整条链子判回去。",
      en: "Measure the bones — re-strike all sixteen exhibits and their p99s; a single REGRESSION row (exhibit #4) is enough to hold the whole lane.",
    },
    fields: ["evidence_dir", "rounds", "verdict", "detail", "report_path"],
    live: null,
  },
  {
    id: "purity",
    file: "agent/graphs/purity_graph.py",
    stateName: "PurityState(TypedDict, total=False)",
    chain: ["intake", "scan", "crosscheck", "verdict", "report", "END"],
    verdicts: { zh: "CLEAR / DIRTY / EVIDENCE-MISSING", en: "CLEAR / DIRTY / EVIDENCE-MISSING" },
    role: {
      zh: "验血——扫描 2,821 个 tracked 文件，0 命中 = CLEAR；任何一处 key 泄漏都是 DIRTY，判词不会客气。",
      en: "The blood test — 2,821 tracked files swept, 0 hits = CLEAR; any single key belched out is DIRTY, and this graph does not negotiate.",
    },
    fields: ["tracked_files", "hits", "verdict", "detail", "report_path"],
    live: null,
  },
  {
    id: "auditor",
    file: "agent/graphs/auditor_graph.py",
    stateName: "AuditChainState(TypedDict, total=False)",
    chain: ["unsigned", "court_lock", "evidence", "scratch_residue", "portfolio", "verdict", "report", "END"],
    verdicts: { zh: "CLEAR / BROKEN", en: "CLEAR / BROKEN" },
    role: {
      zh: "五扇门一次敲——签名 / court 锁 / 证据 / 残留 / portfolio token；一扇红门全链判回。",
      en: "Five doors, one knock — signature / court lock / evidence / residue / portfolio token; one red door and the whole chain says BROKEN.",
    },
    fields: ["unsigned_json", "lock", "evidence_verdict", "residue_hits", "portfolio_state", "verdict", "report_path"],
    live: null,
  },
  {
    id: "night_watch",
    file: "agent/graphs/night_watch_graph.py",
    stateName: "NightWatchState(TypedDict, total=False)",
    chain: ["evidence", "purity", "audit", "verdict", "report", "END"],
    verdicts: { zh: "CLEAR / CRACKED", en: "CLEAR / CRACKED" },
    role: {
      zh: "巡夜——证据 ∩ 纯度 ∩ 审链三个大状态图压在一起；证据不对就 CRACKED；exhibit #4 一条 REGRESSION 够了。",
      en: "The night shift — the three big StateGraphs (evidence · purity · audit) wired onto one spine; one REGRESSION in the evidence lane is enough to keep the watch CRACKED.",
    },
    fields: ["evidence_verdict", "purity_verdict", "audit_verdict", "verdict", "findings", "report_path", "generated_utc"],
    live: liveNightWatch,
  },
  {
    id: "cache_witness",
    file: "agent/graphs/cache_witness_graph.py",
    stateName: "CacheWitnessState(TypedDict, total=False)",
    chain: ["intake", "strike_one", "strike_two", "verdict", "report", "END"],
    verdicts: { zh: "HIT / MISS", en: "HIT / MISS" },
    role: {
      zh: "量前缀缓存——同一段固定提示连敲两下，第二下回来的 cached_tokens 就是全部表态：≥50% 记 HIT。这本书里唯一出网的一张图，按设计敲你的模型车道、朝你数缓存。",
      en: "Measure the prefix cache — strike the same fixed prompt twice and read cached_tokens on the second strike; HIT if it carries more than half. The one networked graph in this book, networked on purpose: it strikes your model lane to count the cache.",
    },
    fields: ["started_utc", "prompt_tokens_a", "cached_tokens_a", "prompt_tokens_b", "cached_tokens_b", "hit_rate_b", "verdict"],
    live: liveCacheWitness,
  },
  {
    id: "insight_advice",
    file: "agent/graphs/insight_advice_graph.py",
    stateName: "AdviceWitnessState(TypedDict, total=False)",
    chain: ["intake", "strike", "verdict", "report", "END"],
    verdicts: { zh: "ANSWERED / UNAVAILABLE", en: "ANSWERED / UNAVAILABLE" },
    role: {
      zh: "盯洞察舱——用面板上同一份匿名聚合包敲一遍模型（合成人群逐字派生 + 本机真实热度 count）：ANSWERED 是模型答出来了，UNAVAILABLE 是诚实沉默；它判词的验收餐厅不出内容——只盯车道畅通。",
      en: "Watch the deck — strike the model once with the same allowlisted aggregate packet the panel renders (synthetic cohort re-derived verbatim + this browser's taps as counts): ANSWERED means the model answered; UNAVAILABLE means an honest silence — the graph never grades content, it watches the lane.",
    },
    fields: ["packet_chars", "fingerprint", "model", "latency_ms", "prompt_tokens", "completion_tokens", "reasoning_tokens", "cached_tokens", "advice_chars", "verdict"],
    live: liveInsightAdvice,
  },
  {
    id: "usage_ledger",
    file: "agent/graphs/usage_ledger_graph.py",
    stateName: "UsageLedgerState(TypedDict, total=False)",
    chain: ["intake", "strike", "verdict", "report", "END"],
    verdicts: { zh: "ANSWERED / UNAVAILABLE", en: "ANSWERED / UNAVAILABLE" },
    role: {
      zh: "读账自陈——离线读本机 token 级用量账本（.local/llm_usage.jsonl），同一套 Usage 面板的诚实口径：车道×协议两簿、错误计数、缓存基数（basis）、占比——报的是它读到的，不是它想明白的；读不到就是 UNAVAILABLE。永不敲模型、永不挑阈值、永不碰 court。",
      en: "The ledger reports itself — read the local token-level ledger with the same honest accounting the Usage panel renders (by_lane × by_protocol, error counting, hit-rate basis, ratios): it reports what it read, never what it intuited; unreadable means UNAVAILABLE. Never strikes the model, never moves a threshold, never touches court.",
    },
    fields: ["window_hours", "started_utc", "summary", "rows_read", "verdict", "report_path"],
    live: liveUsageLedger,
  },
  {
    id: "investigation_dig",
    file: "agent/graphs/investigation_dig_graph.py",
    stateName: "InvestigationDigState(TypedDict, total=False)",
    chain: ["intake", "strike", "verdict", "report", "END"],
    verdicts: { zh: "EVIDENCE-GATHERED / INSUFFICIENT", en: "EVIDENCE-GATHERED / INSUFFICIENT" },
    role: {
      zh: "三人同时入屋——explorer / tester / security 三位只读调查员并行问这个仓库一个问题，看模型能不能带回真证据。耗用的每个月光都记在 usage_ledger；INSUFFICIENT 不逼模型硬答、EVIDENCE-GATHERED 也不替人加分的边界全照实写。",
      en: "Three investigators knock at once — explorer, tester and security readonly investigators fan out in parallel on one question and come back with what they actually found. Every token spent rides into the usage ledger; INSUFFICIENT never pushes the model to bluff, EVIDENCE-GATHERED never upgrades what the model merely implied.",
    },
    fields: ["question", "agents", "findings", "total_tokens_used", "generation_time_ms", "verdict"],
    live: liveInvestigationDig,
  },
  {
    id: "runbook_triage",
    file: "agent/graphs/runbook_triage_graph.py",
    stateName: "RunbookTriageState(TypedDict, total=False)",
    chain: ["intake", "strike", "verdict", "report", "END"],
    verdicts: { zh: "CONFIRMED / INCONCLUSIVE", en: "CONFIRMED / INCONCLUSIVE" },
    role: {
      zh: "探针一响，模型先读仓库——alerts-slo 一条规则 × 最近 20 次提交 × 最新五份证据 × compose 的脱敏环境变量，三条并行车道一起敲模型：先看什么、警报在说什么、仓库里哪一行支持——模型停止之前仓库替它画得出来；CONFIRMED 是模型把证据摆得出来，INCONCLUSIVE 是它如实说它不知道。永远不替 READ 涂绿。",
      en: "The alert fires; the model reads the repo first — one alerts-slo rule × the last twenty commits × the newest five evidence files × the redacted compose api environment, struck as three parallel readonly lanes. CONFIRMED is the model laying the evidence on the table; INCONCLUSIVE is the model saying honestly that it does not know. Never painted jade for a read path.",
    },
    fields: ["alert", "agents", "findings", "total_tokens_used", "generation_time_ms", "verdict"],
    live: liveRunbookTriage,
  },
  {
    id: "exhibit_copilot",
    file: "agent/graphs/exhibit_copilot_graph.py",
    stateName: "ExhibitCopilotState(TypedDict, total=False)",
    chain: ["intake", "strike", "verify", "verdict", "report", "END"],
    verdicts: { zh: "HELD / DRIFTED", en: "HELD / DRIFTED" },
    role: {
      zh: "展厅副驾驶——展的那一侧的灯。每敲一次风压试、证据一落册，模型（只在显式 --live 下）读取那份裁好的 packet：只能引用包内数字、只能用包内形状和差值，不许一个包外数字、不许超过中文 200 字 / 英文 150 词、不许 markdown 标记——越界即 DRIFTED。从不敲 court、从不下判词、从不碰任何合并决定。",
      en: "The exhibit co-pilot — the lamp on the exhibit's own side of the door. Once the stress gauntlet lands its evidence, the model (only under an explicit --live) reads the trimmed packet: numbers must come from the packet, shapes must come from it, deltas must come from it — one out-of-packet digit, one over-ceiling line, one stray markdown marker and the mechanical gate stamps DRIFTED. Never touches court, never writes a verdict, never votes on a merge.",
    },
    fields: ["packet_ok", "pinned", "verdict", "sealed_answer", "sealed_failures", "cached_tokens", "reasoning_tokens", "prompt_tokens"],
    live: liveExhibitCopilot,
  },
  {
    id: "covenant_witness",
    file: "agent/graphs/covenant_witness_graph.py",
    stateName: "CovenantWitnessState(TypedDict, total=False)",
    chain: ["intake", "verify", "verdict", "report", "END"],
    verdicts: { zh: "HELD / DRIFTED", en: "HELD / DRIFTED" },
    role: {
      zh: "行宪见证——这一页五条车道之首的那段字节恒定中文宪章：sha256 逐字 pin 在 #1969 落册日。谁删了一个字、挪了一个空格，verdict 就翻成 DRIFTED；永不敲模型、永不评内容、永不碰 court。",
      en: "The covenant witness — the byte-identical Chinese charter at the head of those five cacheable lanes. sha256 pinned verbatim to its #1969 drop day. One byte moves, one comma swaps — verdict flips to DRIFTED. Never strikes a model, never grades content, never touches court.",
    },
    fields: ["bytes", "sha256", "laws", "referenced_paths", "missing_paths", "pinned", "verdict"],
    live: liveCovenantWitness,
  },
  {
    id: "ask_the_book",
    file: "agent/graphs/ask_the_book_graph.py",
    stateName: "AskTheBookState(TypedDict, total=False)",
    chain: ["intake", "strike", "verify", "verdict", "report", "END"],
    verdicts: { zh: "HELD / DRIFTED", en: "HELD / DRIFTED" },
    role: {
      zh: "问书——公开车道。任何人就该世界书提问，模型整本读过后只复述账本：书里没写就说没写，包外一个字都不给编，判词永远不出自模型。`--live` 显式才敲，offline 默认不联网。",
      en: "Ask the book — the public lane. Anyone asks the world book a question; the model has read the whole thing and may only retell it: unwritten means it says so, not one digit off-packet is tolerated, and the verdict never comes from the model. On-demand `--live` only; offline by default.",
    },
    fields: ["pinned", "prefix_identity_ok", "sanitizer_ok", "fingerprint_ok", "messages_shape_ok", "verdict", "report_path", "live_requested"],
    live: null,
  },
  {
    id: "next_step",
    file: "agent/graphs/next_step_graph.py",
    stateName: "NextStepState(TypedDict, total=False)",
    chain: ["intake", "strike", "verify", "verdict", "report", "END"],
    verdicts: { zh: "HELD / DRIFTED", en: "HELD / DRIFTED" },
    role: {
      zh: "读账——这本书读自己的账本。证据包现算自仓库本身（commits / chronicle / worldbook / library / unit tests，永远是新鲜数字），模型只许引用包内数字，说这本书接下来最值得落一笔什么；包不够厚就直说不够。`--live` 显式才敲。",
      en: "Read the ledger — the book reads its own ledger. The packet is computed from the repo tree at call time (commits / chronicle / worldbook / library / unit tests — always fresh numbers); the model may only quote packet numbers and name the next most worthwhile strike; if the packet cannot support it, it says so. On-demand `--live` only.",
    },
    fields: ["pinned", "packet_identical", "messages_shape_ok", "verdict", "report_path", "live_requested", "zh_cached_tokens", "en_cached_tokens"],
    live: null,
  },
  {
    id: "stress_digest",
    file: "agent/graphs/stress_digest_graph.py",
    stateName: "StressDigestState(TypedDict, total=False)",
    chain: ["intake", "strike", "verify", "verdict", "report", "END"],
    verdicts: { zh: "HELD / DRIFTED", en: "HELD / DRIFTED" },
    role: {
      zh: "读数——周压测的读数员。k6 打完后现读 docs/evidence/weekly-*.json（p99 / err_rate / 诚实行）：这敲干净还是有伤、距 5000ms 机器地板多远，最多三条落在包内数字上的下一步；地板是地板不是 SLO，判词不出现。离线默认；`--live` 显式才敲。",
      en: "The strike, read aloud — the weekly k6 numbers get a reader. It reads docs/evidence/weekly-*.json straight off the disk (p99 / err_rate / the verbatim honesty line): clean or wounded, how much headroom against the 5000 ms machine floor, at most three next actions grounded in packet numbers; the floor is a floor, not an SLO. Offline by default; `--live` only on demand.",
    },
    fields: ["pinned", "packet_identical", "messages_shape_ok", "verdict", "report_path", "live_requested", "zh_cached_tokens", "en_cached_tokens"],
    live: null,
  },
  {
    id: "model_router",
    file: "agent/graphs/model_router_graph.py",
    stateName: "ModelRouterState(TypedDict, total=False)",
    chain: ["intake", "route", "route→evidence|worldbook|nextstep", "guard", "report", "END"],
    verdicts: { zh: "HELD / ROUTE-DRIFT / VERDICT-LEAK / MODEL-FAILURE", en: "HELD / ROUTE-DRIFT / VERDICT-LEAK / MODEL-FAILURE" },
    role: {
      zh: "择路——这一盏和别的见证图不同：模型本身就是路由。它用严格 JSON 选出 evidence / worldbook / nextstep 一条车道，条件边照它的选择跳到下一状态，分支节点再由模型写出中英文内容。三条护栏不让幻觉路由越图、不让模型替展品下判决、失败就诚实报 DRIFT。默认离线见证零 token；LIVE=1 才真敲模型，复用冻结前缀与缓存键，实测一次 168,616 上下文 token、模型判 route=evidence、HELD。",
      en: "The router — unlike the witness graphs, here the MODEL is the router. Strict JSON picks evidence / worldbook / nextstep; a conditional edge follows that choice to the next state, and the branch node writes the Chinese/English content. Three guards: a hallucinated route cannot escape, the model never rules on an exhibit, failure is an honest DRIFT. Offline witness by default (zero token); LIVE=1 strikes the real model on the frozen prefix — one measured run: 168,616 context tokens, model chose route=evidence, HELD.",
    },
    fields: ["route", "route_source", "route_raw", "rationale", "content", "model", "usage", "verdict", "detail", "report_path", "live"],
    live: {
      zh: "实测：prompt 168,616 · completion 77 · 模型判 route=evidence（allowlist 内）· 内容落地 · HELD · 缓存命中读双形状 usage",
      en: "Measured: prompt 168,616 · completion 77 · model chose route=evidence (allowlisted) · content written · HELD · cache read from both usage shapes",
    },
  },
];
