import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { DRILL, TIERS, readDrillRecord, tierIndexFor, writeDrillRecord } from "./drill.copy";
import { DRILL_QUESTIONS, DRILL_TOTAL } from "./drillQuestions";
import "../styles/drill.css";

type Phase = "idle" | "playing" | "done";

/**
 * 验收快问 — The Verify Drill
 *
 * Twelve questions every SpecProof regular should survive half-asleep.
 * Answers lock on first pick; the teacher always speaks, right or wrong.
 * Best score and runs persist under specproof_drill_v1 — the drill never
 * invents your standing.
 */
export default function Drill() {
  const { locale } = useI18n();
  const [phase, setPhase] = useState<Phase>("idle");
  const [idx, setIdx] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);
  const [streak, setStreak] = useState(0);
  const [answers, setAnswers] = useState<boolean[]>([]);
  const [record, setRecord] = useState(() => readDrillRecord());
  const [newBest, setNewBest] = useState(false);
  const [nudge, setNudge] = useState(false);

  const question = DRILL_QUESTIONS[idx];
  const finished = answers.length;

  function bestOf(best: number, current: number): number {
    return Math.max(best, current);
  }

  // re-read the stored best when a run ends so /drill never lies about standing
  function finish() {
    const finalScore = answers.filter(Boolean).length;
    const best = Math.max(record.best, finalScore);
    const moved = best > record.best;
    const next = { best, runs: record.runs + 1 };
    writeDrillRecord(next);
    setRecord(next);
    setNewBest(moved);
    setPhase("done");
  }

  function start() {
    setPhase("playing");
    setIdx(0);
    setPicked(null);
    setStreak(0);
    setAnswers([]);
    setNewBest(false);
    setNudge(false);
  }

  function choose(choice: number) {
    if (picked !== null) return;
    setPicked(choice);
    const ok = choice === question.answer;
    setStreak((s) => (ok ? s + 1 : 0));
    setAnswers((a) => [...a, ok]);
  }

  function next() {
    if (picked === null) {
      setNudge(true);
      window.setTimeout(() => setNudge(false), 1400);
      return;
    }
    setPicked(null);
    if (idx + 1 < DRILL_TOTAL) setIdx(idx + 1);
    else finish();
  }

  // keyboard: 1-4 / a-d answer, Enter advances, never skips a question
  useEffect(() => {
    if (phase !== "playing") return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      const pick = { "1": 0, "2": 1, "3": 2, "4": 3, a: 0, b: 1, c: 2, d: 3 } as Record<string, number>;
      const key = e.key.toLowerCase();
      if (key in pick) {
        e.preventDefault();
        choose(pick[key]);
      } else if (e.key === "Enter") {
        e.preventDefault();
        next();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const fmt = (tpl: string, vars: Record<string, string | number>) =>
    Object.entries(vars).reduce((acc, [k, v]) => acc.split("{" + k + "}").join(String(v)), tpl);

  if (phase === "idle") {
    return (
      <div className="drill-page">
        <div className="page-head">
          <h1>{DRILL.title[locale]} <span className="drill-en">{DRILL.subtitle[locale]}</span></h1>
          <div className="page-sub">{DRILL.lead[locale]}</div>
        </div>

        <div className="drill-hero">
          <div className="drill-hero-copy">
            <p className="drill-kicker">{DRILL.titleNote[locale]}</p>
            <p className="drill-hint">{DRILL.keyboardHint[locale]}</p>
            <div className="drill-stats">
              <div><strong>{record.best}</strong><span>{DRILL.best[locale]}</span></div>
              <div><strong>{record.runs}</strong><span>{DRILL.runs[locale]}</span></div>
            </div>
            <button type="button" className="btn btn-primary drill-start" onClick={start}>{DRILL.start[locale]}</button>
          </div>
          <div className="drill-seal-ladder" aria-hidden="true">
            {TIERS.map((tierDef) => {
              const active = tierIndexFor(record.best) >= TIERS.indexOf(tierDef);
              return (
                <div key={tierDef.at} className={"drill-seal" + (active ? " drill-seal-earned" : "")}>
                  <span className="drill-seal-mark">{tierDef.at === 12 ? "铁" : tierDef.at === 9 ? "印" : tierDef.at === 6 ? "验" : "见"}</span>
                  <span className="drill-seal-name">{tierDef[locale]}</span>
                  <span className="drill-seal-note">{tierDef.note[locale]}</span>
                  <span className="drill-seal-at">{tierDef.at}+</span>
                </div>
              );
            })}
            <p className="drill-seal-rule">{DRILL.sealRule[locale]}</p>
          </div>
        </div>
      </div>
    );
  }

  if (phase === "done") {
    const finalScore = answers.filter(Boolean).length;
    const sealed = tierIndexFor(bestOf(record.best, finalScore));
    const wrong = DRILL_QUESTIONS.filter((_, i) => answers[i] === false);
    return (
      <div className="drill-page">
        <div className="page-head">
          <h1>{DRILL.resultTitle[locale]}</h1>
          <div className="page-sub">{DRILL.titleNote[locale]}</div>
        </div>
        <div className="drill-done">
          <div className="drill-done-seal" data-tier={sealed}>
            <span className="drill-done-mark">{["见", "验", "印", "铁"][sealed]}</span>
            <div>
              <div className="drill-done-score">{fmt(DRILL.scoreLine[locale], { n: finalScore })}</div>
              <div className="drill-done-tier">{TIERS[sealed][locale]}</div>
              <div className="drill-done-note">{TIERS[sealed].note[locale]}</div>
              {newBest ? <div className="drill-done-best">{DRILL.newBest[locale]}</div> : null}
            </div>
          </div>

          <div className="drill-review">
            <h2>{wrong.length === 0 ? DRILL.mistakesNone[locale] : DRILL.mistakesTitle[locale]}</h2>
            {wrong.map((q) => (
              <div key={q.id} className="drill-review-row">
                <div className="drill-review-q">{q.prompt[locale]}</div>
                <div className="drill-review-a">✓ {q.choices[locale][q.answer]}</div>
                <div className="drill-review-teach">{DRILL.teachTitle[locale]} · {q.teach[locale]}</div>
              </div>
            ))}
          </div>

          <div className="drill-done-actions">
            <button type="button" className="btn btn-primary" onClick={start}>{DRILL.again[locale]}</button>
            <a className="btn btn-ghost" href="#/tour">{DRILL.tourCta[locale]}</a>
          </div>
        </div>
      </div>
    );
  }

  const locked = picked !== null;
  const isLast = idx + 1 === DRILL_TOTAL;

  return (
    <div className="drill-page">
      <div className="page-head drill-head-row">
        <h1>{DRILL.title[locale]} <span className="drill-en">{DRILL.subtitle[locale]}</span></h1>
        <div className="drill-chip-row">
          <span className="drill-chip">{fmt(DRILL.question[locale], { n: idx + 1 })}</span>
          <span className="drill-chip drill-chip-streak" data-active={streak >= 3}>{DRILL.streak[locale]} ×{streak}</span>
        </div>
      </div>

      <div className="drill-progress" role="progressbar" aria-valuemin={0} aria-valuemax={DRILL_TOTAL} aria-valuenow={idx}>
        <div style={{ width: `${(idx / DRILL_TOTAL) * 100}%` }} />
      </div>

      <div className="drill-card">
        <p className="drill-prompt">{question.prompt[locale]}</p>
        <div className="drill-choices" role="group" aria-label={question.prompt[locale]}>
          {question.choices[locale].map((choice, i) => {
            const answeredRight = locked && i === question.answer;
            const answeredWrong = locked && i === picked && picked !== question.answer;
            const cls = ["drill-choice"];
            if (answeredRight) cls.push("drill-choice-right");
            if (answeredWrong) cls.push("drill-choice-wrong");
            if (locked && !answeredRight && !answeredWrong) cls.push("drill-choice-dim");
            return (
              <button key={i} type="button" className={cls.join(" ")} onClick={() => choose(i)} aria-pressed={picked === i} disabled={locked}>
                <span className="drill-choice-key" aria-hidden="true">{i + 1}</span>
                <span className="drill-choice-text">{choice}</span>
              </button>
            );
          })}
        </div>

        {locked ? (
          <div className={"drill-teach " + (answers[answers.length - 1] ? "drill-teach-right" : "drill-teach-wrong")}>
            <div className="drill-teach-head">
              <strong>{answers[answers.length - 1] ? DRILL.correct[locale] : DRILL.wrong[locale]}</strong>
              <span className="drill-teach-label">{DRILL.teachTitle[locale]}</span>
            </div>
            <p>{question.teach[locale]}</p>
          </div>
        ) : (
          <div className="drill-teach drill-teach-idle">{nudge ? DRILL.unansweredFirst[locale] : DRILL.keyboardHint[locale]}</div>
        )}

        <div className="drill-actions">
          <span className="drill-counter">{finished}/{DRILL_TOTAL}</span>
          <button type="button" className="btn btn-primary" onClick={next}>{isLast ? DRILL.finish[locale] : DRILL.next[locale]}</button>
        </div>
      </div>
    </div>
  );
}
