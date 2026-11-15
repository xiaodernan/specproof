import { useCallback, useState } from "react";
import { useI18n } from "../i18n";
import worldbook from "./worldbook.json";
import dossier from "./dossier.json";
import chronicle from "./chronicle.json";
import WeeklyVoyage from "./WeeklyVoyage";
import { ProductIcon } from "../ui/ProductIcon";
import "../styles/last-call.css";

/**
 * The Last Call — a serendipity window onto the project's own archives.
 * Three honest draws, restless of your control:
 *
 *   1. One sentence spilled from THE WORLD BOOK (random volume)
 *   2. One golden case drawn at the rail (random case)
 *   3. One ledger section from the chronicle (random entry)
 *
 * No LLM, no network, no curation — this is a lottery of what actually
 * lives in this repository, not a recommendation. Reshuffle is a fresh
 * independent draw; nothing here is "for you", which is the point —
 * something here might be anyway.
 */

type WB = typeof worldbook;
type CaseEntry = (typeof dossier)["cases"][number];
type ChronEntry = (typeof chronicle)[number];
const volumes = (worldbook as WB).locales["zh"].volumes;
const volumesEn = (worldbook as WB).locales["en"].volumes;
const cases = (dossier as { cases: CaseEntry[] }).cases;
const entries = chronicle as ChronEntry[];

const pick = <T,>(arr: T[]): T => arr[Math.floor(Math.random() * arr.length)];

function excerpt(markdown: string, budget: number): string {
  const flat = markdown
    .replace(/^>\s?/gm, "") // drop blockquote markers
    .replace(/`{1,3}/g, "") // drop code fences / backticks
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);
  const prose = (flat.find((p) => !p.startsWith("#") && !p.startsWith("|") && p.length > 24) ?? flat[0] ?? "").replace(/\s+/g, " ");
  return prose.length > budget ? prose.slice(0, budget - 1).trimEnd() + "…" : prose;
}

interface Serving {
  volume: { id: string; title: string; excerpt: string };
  golden: { id: string; family: string; severity: string; title: string; detect: boolean };
  entry: { n: number; t: string };
}

function draw(lang: "zh" | "en"): Serving {
  const w = pick(lang === "zh" ? volumes : volumesEn);
  const g = pick(cases);
  const e = entries.length ? pick(entries) : { n: 0, t: "" };
  return {
    volume: { id: w.num ? "卷" + w.num : w.id, title: w.title, excerpt: excerpt(w.markdown, lang === "zh" ? 150 : 280) },
    golden: { id: g.id, family: g.family, severity: g.severity, title: g.title, detect: g.should_detect },
    entry: { n: e.n, t: e.t },
  };
}

export default function LastCall(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string): string => (zh ? a : b);
  const [serving, setServing] = useState<Serving>(() => draw(locale));

  const reshuffle = useCallback(() => setServing(draw(locale)), [locale]);

  return (
    <div className="last-call-page">
      <header className="last-call-mast">
        <p className="last-call-kicker">{L("末 班 车", "THE LAST CALL")}</p>
        <h1>
          {L("末班车", "Last Call")}
          <span className="last-call-en">{L("THE LAST CALL — THREE INDEPENDENT DRAWS", "末班车 · 三张独立抽牌")}</span>
        </h1>
        <p className="last-call-lead">
          {L(
            "每次开机，这里递给你三张来自本仓库自己的抽牌：一句世界书的溢出、一件金案、一节编年史。没有 LLM 裁决要给你「你需要什么」——这是一场豪赌，看看会不会恰好撞上你正需要的那件东西。",
            "Every visit deals you three independent draws from this repository's own pockets: one sentence spilled from the world book, one golden case, one chronicle entry. No LLM decides what you “need” — it is a lottery, which might just land on the thing you were looking for.",
          )}
        </p>
        <div className="last-call-facts">
          <span>{L("世界书", "world book")} <strong>{volumes.length}</strong> {L("卷", "volumes")}</span>
          <span className="last-call-dot">·</span>
          <span>{L("编年史", "chronicle")} <strong>{entries.length}</strong> {L("节", "sections")}</span>
          <span className="last-call-dot">·</span>
          <span>{L("金案谱", "dossier")} <strong>{cases.length}</strong> {L("件", "cases")}</span>
        </div>
        <button className="last-call-serve" onClick={reshuffle}>
          {L("末班车再开一次", "Run the last call again")}
        </button>
      </header>

      <WeeklyVoyage />
      <div className="last-call-cards">
        <article className="last-call-card last-call-card-book">
          <p className="last-call-card-kicker">{L("世界书的一次抽见", "A SPILL FROM THE WORLD BOOK")}</p>
          <h2>{serving.volume.title}</h2>
          <p className="last-call-excerpt">{serving.volume.excerpt}</p>
          <p className="last-call-card-foot">
            <span>{serving.volume.id}</span>
            <a href="#/worldbook">{L("去世界书翻这一卷 →", "Open this volume →")}</a>
          </p>
        </article>

        <article className="last-call-card last-call-card-case">
          <p className="last-call-card-kicker">{L("金案的一次抽见", "A GOLDEN CASE AT THE RAIL")}</p>
          <h2>{serving.golden.title}</h2>
          <p className="last-call-meta">
            <span className="last-call-pill">{serving.golden.id}</span>
            <span className="last-call-pill last-call-pill-family">{serving.golden.family}</span>
            <span className="last-call-pill last-call-pill-severity">{serving.golden.severity}</span>
            <span className={"last-call-pill " + (serving.golden.detect ? "last-call-pill-detect" : "last-call-pill-negative")}>
              {serving.golden.detect ? L("应被检出", "should detect") : L("阴性对照", "control")}
            </span>
          </p>
          <p className="last-call-card-foot">
            <span>{L("真实文件，不必相信这一句:", "real fixture — check, don't trust:")} <code>git show</code></span>
            <a href="#/dossier">{L("去金案谱翻这一案 →", "Open this case →")}</a>
          </p>
        </article>

        <article className="last-call-card last-call-card-chronicle">
          <p className="last-call-card-kicker">{L("编年史里翻出的一节", "A SECTION FROM THE CHRONICLE")}</p>
          <h2 className="last-call-entry">#{serving.entry.n}</h2>
          <p className="last-call-excerpt">{serving.entry.t}</p>
          <p className="last-call-card-foot">
            <span>{L("第几次提交的编年节，正史入账本", "a section of the ledger; the history of one entry")}</span>
            <a href="#/chronicle">{L("去看它在编年史里的位置 →", "See where it sits in the chronicle →")}</a>
          </p>
        </article>
      </div>

      <footer className="last-call-honesty">
        <ProductIcon name="shield" size={13} />
        <p>
          {zh
            ? "三张抽牌全部独立随机，不挑时机、不挑场合、不向任何人推荐。它们不是营销文案：世界书里每一字节都可 git show，金案里每一案都可验证，编年史里每一节都按 `## #NNNN` 编号入册。它们甚至不保证有趣——保证的是真。"
            : "Three cards, three independent random draws — no timing, no occasion, no recommendation engine. Nothing here is marketing copy: every byte of the world book can be git shown; every golden case can be verified; every chronicle section is numbered `## #NNNN` in the ledger. They do not promise interesting — they guarantee true."}
        </p>
      </footer>
    </div>
  );
}
