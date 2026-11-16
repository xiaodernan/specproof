import type { Locale } from "../i18n/strings";
import nightWatch from "./night_watch.json";
import cacheWitness from "./cache_witness.json";

/**
 * 状态图谱 · The State Graphs — everything this page says is either
 * copied verbatim from the six graphs in `agent/graphs/`, or is a concept
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
      zh: "LangGraph 的每个字段都是一条通道；append 是 reducer（比如 add_messages）。这本书的六个图全是 overwrite 通道——没有对话，不需要累积。",
      en: "Every field in LangGraph is a channel; append is a reducer (add_messages). All six graphs in this book use overwrite channels — there is no dialogue to accumulate.",
    },
  },
  {
    id: "entry",
    term: { zh: "Entry point 入口", en: "Entry point" },
    gloss: {
      zh: "graph.set_entry_point(\"intake\") ——没有 set_entry_point 的图画得出来但跑不起来。六个图的入口全部是 intake / 第一个真相采集节点。",
      en: "graph.set_entry_point(\"intake\") — a graph without an entry point draws fine and runs never. All six graphs enter at intake / the first truth-gathering node.",
    },
  },
  {
    id: "end",
    term: { zh: "END 终态哨兵", en: "END" },
    gloss: {
      zh: "哨兵 END 只做一件事：宣告这一轮结束。它不判断好坏——好坏看 verdict。六张图都以 END 收尾，这是 LangGraph 唯一的硬规则。",
      en: "The sentinel END does one thing: declare this round over. It passes no judgement — the verdict does that. All six graphs end there; it is the one hard rule LangGraph gives you.",
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

const liveNightWatch = {
  zh: `evidence=${NW.lanes?.evidence ?? "?"} · purity=${NW.lanes?.purity ?? "?"} · audit=${NW.lanes?.audit ?? "?"} → ${NW.verdict ?? "?"}（exhibit #4 仍在册）`,
  en: `evidence=${NW.lanes?.evidence ?? "?"} · purity=${NW.lanes?.purity ?? "?"} · audit=${NW.lanes?.audit ?? "?"} → ${NW.verdict ?? "?"} (exhibit #4 still on file)`,
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
];
