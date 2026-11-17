import { Fragment } from "react";
import { useI18n } from "../i18n";
import { CONCEPTS, GRAPHS } from "./stategraph.copy";
import ChainBanner from "./ChainBanner";
import { ProductIcon } from "../ui/ProductIcon";
import "../styles/stategraph.css";

/**
 * 状态图谱 · The State Graphs — a field guide to LangGraph's StateGraph as
 * actually wired inside this repository. Nothing here is tutorial prose from
 * the internet; every concept note maps onto one of the twelve graphs in
 * `agent/graphs/`.
 *
 * The diagrams are boxes-and-arrows because the browser never runs Python.
 * The verdicts printed on the night-watch and cache-witness cards come from the same
 * `night_watch.json` the /engine page reads — git-tracked, verbatim.
 */
export default function StateGraph() {
  const { locale } = useI18n();
  const zh = locale === "zh";

  return (
    <div className="sg-page">
      <div className="page-head">
        <h1>{zh ? "状态图谱" : "The State Graphs"} <span className="sg-en">{zh ? "STATEGRAPHS · LangGraph 现役" : "LANGGRAPH · IN THE ROOM"}</span></h1>
        <div className="page-sub">{zh ? "这本仓库里正在跑的十二个 StateGraph——以及一张读图说明书。不是教程，是验收图纸。" : "The twelve StateGraphs actually wired inside this repository — plus the legend this book reads them by. Not a tutorial — an acceptance drawing."}</div>
      </div>
      <ChainBanner />

      <section className="sg-section">
        <h2>{zh ? "八个必须先会读的词" : "Eight words you must read first"}</h2>
        <ol className="sg-concepts">
          {CONCEPTS.map((c) => (
            <li key={c.id} className="sg-concept" id={"sg-" + c.id}>
              <div className="sg-concept-term">{c.term[locale]}</div>
              <p className="sg-concept-gloss">{c.gloss[locale]}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="sg-section">
        <h2>{zh ? "十二张活着的图" : "The twelve living graphs"}</h2>
        <ol className="sg-graphs">
          {GRAPHS.map((g) => (
            <li key={g.id} className="sg-graph" id={"sg-graph-" + g.id}>
              <div className="sg-graph-head">
                <code className="sg-graph-file">{g.file}</code>
                <div className="sg-graph-state"><ProductIcon name="matrix" size={13} /> {g.stateName}</div>
              </div>
              <div className="sg-chain" role="img" aria-label={zh ? "节点链" : "Node chain"}>
                {g.chain.map((node, i) => (
                  <Fragment key={node + i}>
                    {i > 0 && <span className="sg-chain-arrow" aria-hidden="true">→</span>}
                    <code className={"sg-node" + (node === "END" ? " sg-node-end" : "")}>{node}</code>
                  </Fragment>
                ))}
              </div>
              <p className="sg-graph-role">{g.role[locale]}</p>
              <dl className="sg-graph-meta">
                <div><dt>{zh ? "判词词表" : "Verdict lexicon"}</dt><dd>{g.verdicts[locale]}</dd></div>
                <div><dt>{zh ? "状态字段" : "State fields"}</dt><dd className="sg-fields">{g.fields.map((f) => <code key={f}>{f}</code>)}</dd></div>
                {g.live ? <div><dt>{zh ? "现场判词（本构建快照）" : "Live verdict (this build)"}</dt><dd className="sg-live">{g.live[locale]}</dd></div> : null}
              </dl>
            </li>
          ))}
        </ol>
      </section>

      <section className="sg-section sg-coda">
        <h2>{zh ? "卷末语" : "Colophon"}</h2>
        <p>
          {zh
            ? "这十二张图里七张离线运行；cache_witness、insight_advice 与 investigation_dig 按设计出网；usage_ledger 只读本机账本、不敲车道；runbook_triage 是第十盏灯——按设计出网，探针一响模型先读仓库；covenant_witness 是第十一盏——按 #1969 落册日逐字 pin 住行宪字节，永不敲模型；exhibit_copilot 是第十二盏——`--live` 显式敲一下、模型用展厅风暴的数字写一句自己的展厅铭、包外一个数字都不给过。没有一个判词被涂成绿色。exhibit #4 的 REGRESSION 留在册子里，Night Watch 今天还是 CRACKED。浏览器永不运行 Python——这也是为什么本页用盒子和箭头而不是真实 trace。"
            : "Seven of the twelve graphs run offline. cache_witness, insight_advice and investigation_dig are networked by design — the first strikes this host's model lane to count the prefix cache, the second watches the deck's lane, the third goes out on purpose to ask the repo a question and read what the model brings back; usage_ledger reads the local ledger only and never strikes a lane; runbook_triage is the tenth lamp — networked, fires only after an alert rings, and asks the model to read the repo before humans do; covenant_witness is the eleventh — pinned byte-for-byte to the #1969 charter day, it never strikes a model at all; exhibit_copilot is the twelfth — strikes only on demand, and under one byte-pinned prompt lets the model seal its own exhibit wall in numbers straight from the evidence. No verdict is painted jade. Exhibit #4's REGRESSION is still on file, and tonight's Watch is CRACKED. The browser never runs Python — which is why this page draws boxes and arrows instead of live traces."}
        </p>
        <p className="sg-colophon muted">
          {zh
            ? "LangGraph 的真义不是图，是「状态在节点间只增不乱」的纪律。这本书的每个节点都是一纯函数，每个判词都是 fail-closed——包括你正在读的这一页。"
            : "LangGraph's true meaning is not the picture — it is the discipline of a state that only grows forward, never sideways. Every node here is a pure function; every verdict is fail-closed — including the one rendered on this very page."}
        </p>
      </section>
    </div>
  );
}
