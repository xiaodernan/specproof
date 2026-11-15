import { useI18n } from "../i18n";
import { GRAPH_GROUPS, NODE_INFO } from "./graph.copy";
import "../styles/graph.css";

/**
 * LangGraph view of the SpecProof verify pipeline.
 * A page *about its own engine* — rendered directly from the hand-mirrored
 * copy of agent/graph.py's shape. Re-rendering the real graph automatically
 * would mean running Python in the browser; that is not what we do here.
 * What you see here is a faithful map; what runs behind it is the map you see.
 */
export default function Graph() {
  const { t, locale } = useI18n();
  return (
    <div className="graph-page">
      <div className="page-head">
        <h1>{t("graph.title")} <span className="graph-en">{t("graph.subtitle")}</span></h1>
        <div className="page-sub">{t("graph.lead")}</div>
      </div>

      <ol className="graph-chapters">
        {GRAPH_GROUPS.map((group, gi) => (
          <li key={group.id} className="graph-chapter">
            <div className="graph-chapter-head">
              <span className="graph-chapter-numeral" aria-hidden="true">{["Ⅰ","Ⅱ","Ⅲ","Ⅳ","Ⅴ","Ⅵ"][gi]}</span>
              <div>
                <h2 className="graph-chapter-title">{group.title[locale]}</h2>
                <p className="graph-chapter-blurb">{group.blurb[locale]}</p>
              </div>
            </div>
            <ol className="graph-nodes">
              {group.nodes.map((id) => {
                const node = NODE_INFO[id];
                return (
                  <li key={id} className={"graph-node" + (node.guard ? " graph-node-guard" : "")}>
                    <code className="graph-node-id">{node.label}</code>
                    <p className="graph-node-text">{node.blurb[locale]}</p>
                    {node.guard ? <span className="graph-node-tail">guard</span> : null}
                  </li>
                );
              })}
            </ol>
          </li>
        ))}
      </ol>

      <div className="graph-foot">
        <p>
          <code>agent/graph.py</code> → <code>build_phase0_graph()</code> → <code>StateGraph(Phase0State)</code>.
          {locale === "zh"
            ? " 容易看错的点：这不是“执行列表”，而是状态机——每次执行从初始 state 出发，任何一步都可以把整体直接带到 END。"
            : " What most people miss: this is not a checklist, it is a state machine — every step may fold the whole graph to END."}
        </p>
        <p>
          {locale === "zh"
            ? "条件边：_abort_on_preflight → publish_report（环境缺工具链就直接出炉）、_abort_on_errors → publish_report（任何错误短路跳过）。"
            : "Conditional edges: _abort_on_preflight → publish_report (missing toolchain? skip the whole trial), _abort_on_errors → publish_report (any error short-circuits straight to the verdict)."}
        </p>
        <p>
          {locale === "zh"
            ? "同行的 StateGraph：agent/graphs/evidence_graph.py——本仓库的「证据复核子图」。intake → collect_series → verdict → emit_report → END，一次运行 10ms，逐件敲 docs/evidence/*.json——每逢考核体检，它自己知道答案在 OK 还是 REGRESSION。"
            : "a kin StateGraph lives right here: agent/graphs/evidence_graph.py — the repo's own evidence-review subgraph: intake → collect_series → verdict → emit_report → END; one run, ~10ms; it walks docs/evidence/*.json itself and knows OK from REGRESSION."}
        </p>
      </div>
    </div>
  );
}
