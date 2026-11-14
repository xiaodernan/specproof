import { useEffect, useState } from "react";
import { useNavigate } from "../hooks/navigate";
import { DEMO_AGENT, DEMO_VERIFY, DEMO_VERIFY_ABS_PATH_NOTE } from "../demo";
import { EMPTY_WIZARD_DRAFT, saveWizardDraft } from "../agent/util";
import { apiGet, getApiKey, getBearerToken, type JobsPage } from "../api";
import { Button, GLOSSARY, Kbd } from "../ui";
import {
  EMPTY_PROGRESS,
  ONBOARDING_STEPS,
  loadOnboardingProgress,
  saveOnboardingProgress,
  stepState,
  summarize,
  toggleManualStep,
  type OnboardingProgress,
  type OnboardingStep,
  type OnboardingStepId,
  type OnboardingState,
  type StepSignals,
} from "../ui/onboarding";
import { useI18n } from "../i18n";
import { GUIDE_BY_LOCALE, type GuideCopy } from "./guide.copy";
import "./onboarding.css";

const START_COMMAND = "pwsh scripts/start_local.ps1";

export default function Guide() {
  const { locale } = useI18n();
  const c = GUIDE_BY_LOCALE[locale];
  const [copyState, setCopyState] = useState("");
  const [progress, setProgress] = useState<OnboardingProgress>(EMPTY_PROGRESS);
  const [progressUnreadable, setProgressUnreadable] = useState(false);
  const [connection, setConnection] = useState<"pending" | "ok" | "failed">("pending");
  const [verificationCount, setVerificationCount] = useState<number | null>(null);
  const [saveFailed, setSaveFailed] = useState(false);
  const [credential] = useState<"present" | "absent">(() =>
    getBearerToken() || getApiKey() ? "present" : "absent"
  );
  const navigate = useNavigate();

  useEffect(() => {
    const read = loadOnboardingProgress();
    setProgress(read.progress);
    setProgressUnreadable(read.status === "unreadable");
    // Without a credential the request cannot succeed, and asking anyway would
    // turn "this browser has never logged in" into a red failure. The absence
    // of the credential is the observation we act on.
    if (credential === "absent") return;
    let alive = true;
    // One real request answers two steps: it proves the workspace is
    // reachable, and its total says whether a verification exists yet.
    // `total` ONLY: the probe asks for one row, so the length of `jobs` can
    // never be more than "at least one" — reading it as a count told a
    // workspace with 57 verifications that it had 1.
    apiGet<JobsPage>("/jobs?limit=1")
      .then((data) => {
        if (!alive) return;
        setConnection("ok");
        // Two claims, not one. `JobsPage.total` is required because every exit of the
        // route answers it, so the type says the key cannot be missing; this guard is about
        // the answer, not the declaration -- a body that arrives without the field still
        // lands here, and `null` is the honest reading of that. The checker cannot see this
        // line either way, so `Guide.test.tsx` is its only witness.
        setVerificationCount(typeof data.total === "number" ? data.total : null);
      })
      .catch(() => {
        if (!alive) return;
        // A failed probe leaves both steps "unknown": an unreadable answer is
        // not an answer of "no".
        setConnection("failed");
        setVerificationCount(null);
      });
    return () => {
      alive = false;
    };
  }, [credential]);

  const signals: StepSignals = { progressUnreadable, credential, connection, verificationCount };
  const summary = summarize(ONBOARDING_STEPS, progress, signals);

  const stateLabel: Record<OnboardingState, string> = {
    done: c.stateDone,
    todo: c.stateTodo,
    unknown: c.stateUnknown,
  };

  function tick(stepId: OnboardingStepId) {
    const next = toggleManualStep(progress, stepId, new Date().toISOString());
    setSaveFailed(!saveOnboardingProgress(next));
    setProgress(next);
  }

  function basisNote(step: OnboardingStep, state: OnboardingState): string {
    if (step.id === "connect") {
      if (credential === "absent") return c.connectAbsent;
      if (state !== "unknown") return c.stepBasis.connect ?? "";
      return connection === "pending" ? c.connectPending : c.connectFailed;
    }
    if (step.id === "create_verification") {
      if (state !== "unknown" && verificationCount !== null) {
        return c.countDone(verificationCount);
      }
      if (credential === "absent") return c.countAbsent;
      if (connection === "pending") return c.countPending;
      // An answer without a total is not "unreadable" and not "zero": the
      // workspace replied, it just never said how many there are.
      if (connection === "ok") {
        return c.countNoTotal;
      }
      return c.countFailed;
    }
    return c.stepBasis[step.id] ?? step.basis;
  }

  function startDemoVerify() {
    const query = new URLSearchParams({
      repo: DEMO_VERIFY.repo_path,
      spec: DEMO_VERIFY.spec_path,
      base: DEMO_VERIFY.base_ref,
      head: DEMO_VERIFY.head_ref,
    });
    navigate("/jobs/new?" + query.toString());
  }

  function startDemoAgent() {
    saveWizardDraft({
      ...EMPTY_WIZARD_DRAFT,
      task_name: DEMO_AGENT.task_name,
      spec_text: DEMO_AGENT.spec_text,
    });
    navigate("/agent/new/spec");
  }

  async function copyCommand() {
    try {
      await navigator.clipboard.writeText(START_COMMAND);
      setCopyState(c.copiedOk);
    } catch {
      setCopyState(c.copyFailed);
    }
  }

  return (
    <div className="guide-page">
      <div className="page-head">
        <div className="welcome-eyebrow">{c.eyebrow}</div>
        <h1>{c.title}</h1>
        <p className="guide-intro">{c.intro}</p>
        <div className="guide-actions"><a href="#/jobs/new" className="ui-btn ui-btn-primary ui-btn-md">{c.actionNew}</a><a href="#/dashboard" className="ui-btn ui-btn-secondary ui-btn-md">{c.actionDashboard}</a></div>
      </div>

      <div className="degraded"><strong>{c.degradedStrong}</strong><p>{c.degradedBody}</p></div>
      <section className="guide-choices" aria-label={c.choiceAria}>
        <article className="guide-choice"><span className="guide-kicker">{c.choice1Kicker}</span><h2>{c.choice1Title}</h2><p>{c.choice1Body}</p><a href="#/jobs/new">{c.choice1Link} <span aria-hidden="true">→</span></a></article>
        <article className="guide-choice"><span className="guide-kicker">{c.choice2Kicker}</span><h2>{c.choice2Title}</h2><p>{c.choice2Body}</p><a href="#/agent/new">{c.choice2Link} <span aria-hidden="true">→</span></a></article>
        <article className="guide-choice"><span className="guide-kicker">{c.choice3Kicker}</span><h2>{c.choice3Title}</h2><p>{c.choice3Body}</p><a href="#/jobs">{c.choice3Link} <span aria-hidden="true">→</span></a></article>
      </section>

      <section className="guide-section" aria-labelledby="guide-start">
        <div className="guide-section-head"><span className="guide-section-number">{c.startKicker}</span><div><h2 id="guide-start">{c.startTitle}</h2><p>{c.startBody}</p></div></div>
        <div className="guide-checklist-head">
          <strong>{c.checklistTitle(summary.done, summary.total)}</strong>
          <span>{c.checklistBasis}</span>
          {summary.unknown > 0 ? <span className="guide-checklist-unknown">{c.unknownBadge(summary.unknown)}</span> : null}
        </div>
        {progressUnreadable ? (
          <p className="guide-checklist-warn" role="status">{c.unreadableNote}<strong>{c.unreadableNoteBody}</strong></p>
        ) : null}
        {saveFailed ? (
          <p className="guide-checklist-warn" role="status">{c.saveFailedNote}</p>
        ) : null}
        <ol className="guide-steps guide-steps-checklist">
          {ONBOARDING_STEPS.map((step) => {
            const state = stepState(step, progress, signals);
            return (
              <li key={step.id} className={"guide-step guide-step-" + state}>
                <div className="guide-step-head">
                  {step.evidence === "manual" ? (
                    <label className="guide-step-check">
                      <input
                        type="checkbox"
                        checked={state === "done"}
                        disabled={state === "unknown"}
                        onChange={() => tick(step.id)}
                      />
                      <span>{c.manualCheckbox}</span>
                    </label>
                  ) : (
                    <span className={"guide-step-mark guide-step-mark-" + state} aria-hidden="true">
                      {state === "done" ? "✓" : state === "unknown" ? "?" : ""}
                    </span>
                  )}
                  <strong>{c.stepTitles[step.id] ?? step.title}</strong>
                  <span className={"guide-step-state guide-step-state-" + state}>{stateLabel[state]}</span>
                  {step.evidence === "manual" ? <span className="guide-step-kind">{c.stepkindManual}</span> : <span className="guide-step-kind">{c.stepkindAuto}</span>}
                </div>
                <GuideStepDetail id={step.id} c={c} />
                <p className="guide-step-basis">{basisNote(step, state)}</p>
              </li>
            );
          })}
        </ol>
      </section>

      <section className="guide-section guide-example" aria-labelledby="guide-example">
        <div className="guide-section-head"><span className="guide-section-number">{c.exampleKicker}</span><div><h2 id="guide-example">{c.exampleTitle}</h2><p>{c.exampleBody}</p></div></div>
        <div className="guide-example-grid"><dl><div><dt>{locale === "zh" ? "演示仓库" : "Demo repo"}</dt><dd><code>demo/spring-backend</code></dd></div><div><dt>{locale === "zh" ? "改动前 → 改动后" : "Base → Head"}</dt><dd><code>{DEMO_VERIFY.base_ref} → {DEMO_VERIFY.head_ref}</code></dd></div><div><dt>{locale === "zh" ? "需求文件" : "Requirement file"}</dt><dd><code>demo/requirement.txt</code></dd></div></dl><div className="guide-example-outcome"><span className="guide-kicker">{c.expectedKicker}</span><h3>{c.expectedTitle}</h3><p>{c.expectedBodyBefore}<code>{DEMO_VERIFY.head_ref}</code>{c.expectedBodyAfter}<code>BLOCKED</code>）{locale === "zh" ? "——铁证在手再决定。" : " — the iron speaks first."}</p><div className="guide-example-actions"><Button variant="primary" onClick={startDemoVerify}>{c.verifyNow}</Button><span>{c.demoCommands}<code>pwsh scripts/prepare_demo_repo.ps1</code>{locale === "zh" ? "创建演示仓库" : " to create the demo repo"}{DEMO_VERIFY_ABS_PATH_NOTE}</span></div></div></div>
        <div className="demo-prefill"><strong>{c.demoHeadline}</strong><p>{c.demoBody}</p><div className="demo-prefill-row"><Button size="sm" onClick={startDemoAgent}>{c.demoCta}</Button><span className="demo-prefill-status">{c.demoNote}</span></div></div>
      </section>

      <section className="guide-section" aria-labelledby="guide-results">
        <div className="guide-section-head"><span className="guide-section-number">{c.resultsKicker}</span><div><h2 id="guide-results">{c.resultsTitle}</h2><p>{c.resultsBody}</p></div></div>
        <div className="guide-result-grid">
          <article><span className="guide-result-dot guide-result-ok" /><h3>{c.verdictVerified} <code>VERIFIED</code></h3><p>{c.verdictVerifiedBody}</p></article>
          <article><span className="guide-result-dot guide-result-bad" /><h3>{c.verdictBlocked} <code>BLOCKED</code></h3><p>{c.verdictBlockedBody}</p></article>
          <article><span className="guide-result-dot guide-result-warn" /><h3>{c.verdictFailed} <code>FAILED</code></h3><p>{c.verdictFailedBody}</p></article>
          <article><span className="guide-result-dot" /><h3>{c.verdictUnverified} <code>UNVERIFIED</code></h3><p>{c.verdictUnverifiedBody}</p></article>
        </div>
      </section>

      <section className="guide-section" aria-labelledby="guide-glossary">
        <div className="guide-section-head"><span className="guide-section-number">04</span><div><h2 id="guide-glossary">{c.glossaryTitle}</h2></div></div>
        <dl className="guide-glossary">{guideGlossary(locale, c).map((entry) => <div key={entry.id}><dt>{entry.label}</dt><dd>{entry.definition}</dd></div>)}</dl>
      </section>

      <section className="guide-shortcuts" aria-labelledby="guide-keyboard">
        <h2 id="guide-keyboard">{c.shortcutsTitle}</h2>
        <p>
          {c.shortcutsBodyBefore} <Kbd>?</Kbd> {c.shortcutsBodyMid} <Kbd>Ctrl</Kbd> <Kbd>K</Kbd>。
          {c.shortcutsBodyEnd} <Kbd>Esc</Kbd>{locale === "zh" ? "，随时取消当前动作。" : " — cancel the current action at any time."}
        </p>
      </section>

      <section className="guide-startup" aria-labelledby="guide-local"><div><h2 id="guide-local">{c.localTitle}</h2><p>{c.localBody}</p><code className="guide-command">python -m pip install -e ".[dev]"<br />{START_COMMAND}</code><span role="status" className="guide-copy-status">{copyState}</span></div><Button onClick={() => { void copyCommand(); }}>{c.copyCommand}</Button></section>
    </div>
  );
}

function GuideStepDetail({ id, c }: { id: OnboardingStepId; c: GuideCopy }) {
  if (id === "connect") {
    return localeDetailZh === undefined ? null : connectDetail(id, c);
  }
  return genericDetail(id, c);
}

const connectDetail = (_id: string, c: GuideCopy) => (
  <>{c.connectBodyBefore}<a href="#/settings">{c.connectBodyLink}</a>{c.connectBodyAfter}</>
);
const genericDetail = (id: string, c: GuideCopy) => (
  <>{c.stepDetail[id]}</>
);
// Guarantees TS doesn't flag connectDetail's unused param when refactored.
const localeDetailZh: undefined = undefined;

function guideGlossary(locale: "zh" | "en", c: GuideCopy): { id: string; label: string; definition: string }[] {
  if (locale === "zh") return GLOSSARY.map((entry) => ({ id: entry.id, label: entry.label, definition: entry.definition }));
  return GLOSSARY.map((entry) => {
    const gloss = c.glossaries[entry.id];
    return gloss
      ? { id: entry.id, label: gloss.label, definition: gloss.definition }
      : { id: entry.id, label: entry.en || entry.id, definition: entry.en || entry.id };
  });
}
