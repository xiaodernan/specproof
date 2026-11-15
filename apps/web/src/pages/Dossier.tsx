import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n";
import { ProductIcon } from "../ui/ProductIcon";
import dossier from "./dossier.json";
import "../styles/dossier.css";

/**
 * The Golden Case Compendium — every golden fixture committed to this
 * repository, browsable and searchable in-app.
 *
 * Data source: `scripts/build_dossier.py` reads each case's `ground-truth.json`
 * (and `attribution`, when present) at build time and writes `dossier.json`.
 * Nothing here comes from the network; every number is reproducible from git.
 */

type DossierCase = {
  id: string;
  family: "standard" | "attribution" | "crosslang";
  number: number;
  title: string;
  spec: string;
  severity: string;
  contract: string | null;
  evidence_type: string;
  should_detect: boolean;
  base_ref: string | null;
  head_ref: string | null;
  base_defects: number;
  head_defects: number;
  path: string;
};

const CASES = (dossier as { version: number; cases: DossierCase[] }).cases;

type FamilyFilter = "all" | DossierCase["family"];
type SeverityFilter = "all" | "BLOCKER" | "MAJOR" | "NONE";

const SEV_CLASS: Record<string, string> = {
  BLOCKER: "dossier-sev-blocker",
  MAJOR: "dossier-sev-major",
  MINOR: "dossier-sev-minor",
  NONE: "dossier-sev-none",
};

export default function Dossier(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const [query, setQuery] = useState("");
  const [family, setFamily] = useState<FamilyFilter>("all");
  const [severity, setSeverity] = useState<SeverityFilter>("all");
  const [onlyDetectable, setOnlyDetectable] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  const L = (a: string, b: string): string => (zh ? a : b);

  useEffect(() => {
    document.title = L("金案谱 · SpecProof", "The Golden Case Compendium · SpecProof");
  }, [zh]);

  const stats = useMemo(() => {
    const detect = CASES.filter((c) => c.should_detect).length;
    const blocker = CASES.filter((c) => c.severity === "BLOCKER").length;
    const major = CASES.filter((c) => c.severity === "MAJOR").length;
    const none = CASES.filter((c) => c.severity === "NONE").length;
    return { total: CASES.length, detect, blocker, major, none };
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return CASES.filter((c) => {
      if (family !== "all" && c.family !== family) return false;
      if (severity !== "all" && c.severity !== severity) return false;
      if (onlyDetectable && !c.should_detect) return false;
      if (!q) return true;
      const hay = `${c.id} ${c.title} ${c.spec} ${c.contract ?? ""} ${c.evidence_type} ${c.severity} ${c.path}`.toLowerCase();
      return q.split(/\s+/).every((tok) => hay.includes(tok));
    });
  }, [query, family, severity, onlyDetectable]);

  const familyLabel = (f: DossierCase["family"]): string =>
    zh
      ? { standard: "标准金案", attribution: "归因金案", crosslang: "跨语言金案" }[f]
      : { standard: "standard", attribution: "attribution", crosslang: "crosslang" }[f];

  return (
    <div className="dossier-page">
      <header className="dossier-mast">
        <p className="dossier-kicker">{L("铁 证 案 卷", "THE GOLDEN COMPENDIUM")}</p>
        <h1>
          {L("金案谱", "The Golden Case Compendium")}
          <span className="dossier-en">{L("THE GOLDEN CASE COMPENDIUM", "金案谱 · 铁证案卷")}</span>
        </h1>
        <p className="dossier-lead">
          {L(
            "仓库里真實躺着一百一十一桩金案——标准的、归因的、跨语言的每一件都有 ground-truth.json。这一页把它们逐字列出来：每一案的 Severity、Contract、Evidence_type、能不能被检出，全部从文件当场读取，不经过演示数据，也不经过任何 LLM。",
            "One hundred and eleven golden cases live in this repository — standard, attribution-adjoined, and cross-language — each carrying a ground-truth.json. This page renders them verbatim: severity, contract, evidence_type, detectability — read from the files at build time, never a demo, never an LLM in between.",
          )}
        </p>
        <div className="dossier-stats">
          <div className="dossier-stat"><p className="dossier-stat-v">{stats.total}</p><p className="dossier-stat-l">{L("金案总数", "golden cases")}</p></div>
          <div className="dossier-stat"><p className="dossier-stat-v">{stats.detect}</p><p className="dossier-stat-l">{L("应被检出", "should detect")}</p></div>
          <div className="dossier-stat"><p className="dossier-stat-v">{stats.blocker}</p><p className="dossier-stat-l">BLOCKER</p></div>
          <div className="dossier-stat"><p className="dossier-stat-v">{stats.major}</p><p className="dossier-stat-l">MAJOR</p></div>
          <div className="dossier-stat"><p className="dossier-stat-v">{stats.none}</p><p className="dossier-stat-l">NONE {L("（阴性对照）", "controls")}</p></div>
        </div>
      </header>

      <div className="dossier-controls">
        <input
          className="dossier-search"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={L("搜索案号 / 标题 / 关键词 / 契约 / 证据类型…（空格分词）", "search id / title / keyword / contract / evidence type… (space = AND tokens)")}
          aria-label={L("搜索金案", "search golden cases")}
        />
        <div className="dossier-filters" role="toolbar" aria-label={L("筛选", "filters")}>
          <div className="dossier-filter-group">
            <span className="dossier-filter-label">{L("族", "family")}</span>
            {(["all", "standard", "attribution", "crosslang"] as const).map((f) => (
              <button key={f} className={"dossier-chip" + (family === f ? " dossier-chip-on" : "")} onClick={() => setFamily(f)}>
                {f === "all" ? L("全部", "all") : familyLabel(f)}
              </button>
            ))}
          </div>
          <div className="dossier-filter-group">
            <span className="dossier-filter-label">{L("裁决", "severity")}</span>
            {(["all", "BLOCKER", "MAJOR", "NONE"] as const).map((s) => (
              <button key={s} className={"dossier-chip" + (severity === s ? " dossier-chip-on" : "")} onClick={() => setSeverity(s)}>
                {s === "all" ? L("全部", "all") : s}
              </button>
            ))}
          </div>
          <button
            className={"dossier-chip dossier-chip-toggle" + (onlyDetectable ? " dossier-chip-on" : "")}
            aria-pressed={onlyDetectable}
            onClick={() => setOnlyDetectable((v) => !v)}
          >
            {L("仅看应被检出", "detectable only")}
          </button>
        </div>
        <p className="dossier-count">
          {L("当前可见", "showing")} <strong>{filtered.length}</strong> / {CASES.length} {L("件", "cases")}
        </p>
      </div>

      <div className="dossier-grid">
        {filtered.map((c) => (
          <article key={c.family + "/" + c.id} className="dossier-card">
            <header className="dossier-card-head">
              <span className="dossier-card-id">{c.path.replace(/^golden-cases-?/, "").replace(/^\//, "")}</span>
              <div className="dossier-card-pills">
                <span className="dossier-pill dossier-pill-family">{familyLabel(c.family)}</span>
                <span className={"dossier-pill " + (SEV_CLASS[c.severity] ?? "dossier-sev-minor")}>{c.severity}</span>
                <span className={"dossier-pill dossier-pill-detect" + (c.should_detect ? "" : " dossier-pill-negative")}>
                  {c.should_detect ? L("应检出", "detect") : L("阴性对照", "control")}
                </span>
              </div>
            </header>
            <h2 className="dossier-card-title">{c.title}</h2>
            <p className="dossier-card-meta">
              <span>{c.contract ?? L("无契约（阳性阴性对照）", "no contract (control)")}</span>
              <span className="dossier-dot">·</span>
              <code>{c.evidence_type}</code>
            </p>
            <button
              className="dossier-toggle"
              aria-expanded={open === c.id}
              onClick={() => setOpen((cur) => (cur === c.id ? null : c.id))}
            >
              {open === c.id ? L("收起卷宗", "Collapse dossier") : L("展开卷宗", "Open dossier")}
              <span className="dossier-toggle-caret" aria-hidden="true">{open === c.id ? "▴" : "▾"}</span>
            </button>
            {open === c.id && (
              <div className="dossier-detail">
                <pre className="dossier-spec">{c.spec}</pre>
                <dl className="dossier-truth">
                  <div><dt>{L("期望 severity", "expected severity")}</dt><dd>{c.severity}</dd></div>
                  <div><dt>{L("期望 contract", "expected contract")}</dt><dd>{c.contract ?? "—"}</dd></div>
                  <div><dt>{L("期望证据类型", "expected evidence")}</dt><dd><code>{c.evidence_type}</code></dd></div>
                  <div><dt>base → head</dt><dd><code>{c.base_ref ?? "?"} → {c.head_ref ?? "?"}</code></dd></div>
                  {c.family === "attribution" && (
                    <div><dt>{L("归因缺陷（base/head）", "attribution defects (base/head)")}</dt><dd>{c.base_defects} / {c.head_defects}</dd></div>
                  )}
                </dl>
                <p className="dossier-path"><code>git show HEAD:{c.path}/ground-truth.json</code></p>
              </div>
            )}
          </article>
        ))}
        {filtered.length === 0 && (
          <div className="dossier-empty">
            <ProductIcon name="scroll" size={26} />
            <p>{L("没有任何一案匹配这组筛选条件。", "No case matches that filter.")}</p>
            <button className="dossier-chip" onClick={() => { setQuery(""); setFamily("all"); setSeverity("all"); setOnlyDetectable(false); }}>
              {L("清空筛选", "clear filters")}
            </button>
          </div>
        )}
      </div>

      <footer className="dossier-footer">
        <ProductIcon name="shield" size={13} />
        <p>
          {zh
            ? "一百一十一案全部入库于本仓库（golden-cases / golden-cases-attribution / golden-cases-crosslang），由 scripts/build_golden_scenarios.py 可复现生成、scripts/build_dossier.py 编译成此页；ground-truth 从文件当场读取，渲染不经过任何演示数据，也不经过任何 LLM。打开一案就等于打开一次 git 证词——不信，自己 git show。"
            : "All 111 cases are committed to this repository (golden-cases / golden-cases-attribution / golden-cases-crosslang), rebuilt reproducibly by scripts/build_golden_scenarios.py and compiled to this page by scripts/build_dossier.py; ground truth is read from the files at build time — never demo data, never an LLM in the loop. Opening a case is opening a git testimony; don't take our word, run git show."}
        </p>
      </footer>
    </div>
  );
}
