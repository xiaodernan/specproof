import { useState } from "react";
import { useI18n } from "../i18n";
import { GUESS_CARDS, GUESS_TOTAL } from "./guessCards";
import "../styles/guess.css";

const STORE_KEY = "specproof_guess_v1";
interface Record {
  best: number;
  runs: number;
}

function readRecord(): Record {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (!raw) return { best: 0, runs: 0 };
    const parsed = JSON.parse(raw) as Partial<Record>;
    return {
      best: typeof parsed.best === "number" ? parsed.best : 0,
      runs: typeof parsed.runs === "number" ? parsed.runs : 0,
    };
  } catch {
    return { best: 0, runs: 0 };
  }
}

function writeRecord(r: Record): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(r));
  } catch {
    /* quota — best effort */
  }
}

function Badge({ locale }: { locale: string }) {
  const verdict = locale === "zh" ? "裁判从不侥幸" : "the court is never kind";
  return <span className="guess-badge">{verdict}</span>;
}

function PALMS({ locale }: { locale: string }) {
  return (
    <div className="guess-palms">
      <div className="guess-palms-block">
        <strong>{locale === "zh" ? "accept · 允许合并" : "accept · merge allowed"}</strong>
        <span>{locale === "zh" ? "hops past every spec & evidence gate" : "hops past every spec & evidence gate"}</span>
      </div>
      <div className="guess-palms-block">
        <strong>{locale === "zh" ? "block · 阻断合并" : "block · merge blocked"}</strong>
        <span>{locale === "zh" ? "in evidence-rich repos, the weight of pass is heavy" : "in evidence-rich repos, the weight of pass is heavy"}</span>
      </div>
    </div>
  );
}

export default function GuessTheVerdict() {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const [phase, setPhase] = useState<"idle" | "playing" | "done">("idle");
  const [idx, setIdx] = useState(0);
  const [picked, setPicked] = useState<"accept" | "block" | null>(null);
  const [answers, setAnswers] = useState<boolean[]>([]);
  const [record, setRecord] = useState<Record>(() => readRecord());
  const [newBest, setNewBest] = useState(false);

  const question = GUESS_CARDS[idx];

  function start() {
    setPhase("playing");
    setIdx(0);
    setPicked(null);
    setAnswers([]);
    setNewBest(false);
  }

  function choose(verdict: "accept" | "block") {
    if (picked !== null) return;
    setPicked(verdict);
    setAnswers((a) => [...a, verdict === question.answer]);
  }

  function next() {
    if (idx + 1 < GUESS_TOTAL) {
      setIdx(idx + 1);
      setPicked(null);
    } else {
      const finalScore = answers.filter(Boolean).length + (picked === question.answer ? 1 : 0);
      const still = readRecord();
      const best = Math.max(still.best, finalScore);
      const moved = best > still.best;
      const nextRecord = { best, runs: still.runs + 1 };
      writeRecord(nextRecord);
      setRecord(nextRecord);
      setNewBest(moved);
      setPhase("done");
    }
  }

  if (phase === "idle") {
    return (
      <div className="guess-page">
        <div className="guess-hero">
          <div className="guess-eyebrow">{zh ? "裁判人 · 观众视角" : "The Court, from the audience seats"}</div>
          <h1 className="guess-title">
            {zh ? "猜裁判 · The Verifier" : "Guess the Verdict · The Verifier"}
          </h1>
          <p className="guess-lead">
            {zh
              ? "你面前是一份变更请求 + 一份 SPEC（需求）。SpecProof 的判定不是给点数，而是给门禁——每道题都 anchored 在本仓的世界书卷里。答错了也会把你带到卷里，答对了才更知道红线在哪里。"
              : "Before you is a change request and its SPEC. SpecProof does not score — it gates. Each card anchors in this repo's Bible; wrong answers open the scroll, right ones tell you where the real line is."}
          </p>
          <Badge locale={locale} />
          <div className="guess-stats">
            <div><strong>{record.best}/{GUESS_TOTAL}</strong><span>{zh ? "最高 · best" : "best"}</span></div>
            <div><strong>{record.runs}</strong><span>{zh ? "总回合 · runs" : "runs"}</span></div>
            <div><strong>{GUESS_TOTAL}</strong><span>{zh ? "题数 · cards" : "cards"}</span></div>
          </div>
          <button type="button" className="btn btn-primary guess-start" onClick={start}>
            {zh ? "开始裁判 · Begin" : "Begin · 开始裁判"}
          </button>
          <PALMS locale={locale} />
        </div>
      </div>
    );
  }

  if (phase === "done") {
    const finalScore = answers.filter(Boolean).length;
    return (
      <div className="guess-page">
        <div className="guess-hero">
          <div className="guess-eyebrow">{zh ? "裁判·结账" : "The Court tallies"}</div>
          <h1 className="guess-done-score">{finalScore} / {GUESS_TOTAL}</h1>
          <p className="guess-lead">{newBest ? (zh ? "新纪录 · your best so far." : "New personal best.") : record.best > 0 ? (zh ? `回归 · 你之前最好 ${record.best}/${GUESS_TOTAL}` : `Your prior best stands at ${record.best}/${GUESS_TOTAL}.`) : (zh ? "第一回合初登记 · first run, recorded." : "First run, properly recorded.")}</p>
          {newBest ? <p className="guess-badge">{zh ? "封卷一回" : "One ceremonial stamp"}</p> : null}
          <div className="guess-done-actions">
            <button type="button" className="btn btn-primary" onClick={start}>{zh ? "再来一次 · again" : "Again · 再来一次"}</button>
            <a className="btn btn-ghost" href="#/drill">{zh ? "去验收快问 · Verify Drill" : "Verify Drill · 去验收快问"}</a>
            <a className="btn btn-ghost" href="#/library">{zh ? "去世界书 · Library" : "Library · 去世界书"}</a>
          </div>
        </div>
      </div>
    );
  }

  const isLast = idx + 1 === GUESS_TOTAL;
  const isRight = picked === question.answer;

  return (
    <div className="guess-page">
      <div className="guess-hero guess-round">
        <div className="guess-eyebrow">
          {zh ? `第 ${idx + 1} / ${GUESS_TOTAL} 张 · Card ${idx + 1} of ${GUESS_TOTAL}` : `Card ${idx + 1} of ${GUESS_TOTAL}`}
        </div>
        <h1 className="guess-prompt">{question.prompt[locale]}</h1>

        <div className="guess-evidence">
          <div className="guess-evidence-block">
            <div className="guess-evidence-kicker">{zh ? "change 包" : "change pack"}</div>
            <div className="guess-evidence-body">{question.change[locale]}</div>
          </div>
          <div className="guess-evidence-block">
            <div className="guess-evidence-kicker">{zh ? "spec 包" : "spec pack"}</div>
            <div className="guess-evidence-body">{question.spec[locale]}</div>
          </div>
        </div>

        <div className="guess-buttons" aria-label={zh ? "Choose verdict" : "Choose verdict"}>
          <button type="button" className={"guess-verdict guess-verdict-accept" + (picked === "accept" ? " guess-verdict-picked" : "")} onClick={() => choose("accept")}>
            {zh ? "ACCEPT · 允许" : "ACCEPT · Approve"}
          </button>
          <button type="button" className={"guess-verdict guess-verdict-block" + (picked === "block" ? " guess-verdict-picked" : "")} onClick={() => choose("block")}>
            {zh ? "BLOCK · 阻断" : "BLOCK · Block"}
          </button>
        </div>

        {picked !== null ? (
          <div className={"guess-teach " + (isRight ? "guess-teach-right" : "guess-teach-wrong")}>
            <div className="guess-teach-head">
              <strong>{isRight ? (zh ? "对 · your read matched the court." : "Correct — your read matched the court.") : (zh ? "错 · the court reads it the other way." : "Wrong — the court reads it the other way.")}</strong>
            </div>
            <p>{question.teach[locale]}</p>
          </div>
        ) : null}

        <div className="guess-actions">
          <span className="guess-counter">{answers.filter(Boolean).length}/{GUESS_TOTAL}</span>
          <button type="button" className="btn btn-primary" onClick={next} disabled={picked === null}>
            {isLast ? (zh ? "结算 · finish" : "Finish · 结算") : (zh ? "下一张 · next" : "Next · 下一张")}
          </button>
        </div>
      </div>
    </div>
  );
}
