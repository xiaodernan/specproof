import { useState } from "react";
import { useI18n } from "../i18n";
import { useIdentityAccess } from "../identity/useIdentityAccess";
import { PermissionDenied } from "../identity/PermissionDenied";
import { postInvestigationDig, type InvestigationDig } from "../api";
import { Spinner, Panel, Button } from "../ui";
import "../styles/manual.css";

/**
 * The Dig — ask three readonly investigators a question about this repo.
 *
 * Admin/operator RBAC. This is NOT a verdict engine, NOT a demo mode, NOT a
 * judge. The model sees a bounded fact pack (top-level layout, README
 * headings, tests, python count), answers honestly — or says INSUFFICIENT.
 * No guessing, ever.
 */
export default function Dig() {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const { checked, canManage } = useIdentityAccess();
  const [question, setQuestion] = useState("这仓库在做什么？");
  const [result, setResult] = useState<InvestigationDig | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = async () => {
    const q = question.trim();
    if (!q) return;
    setBusy(true);
    setResult(null);
    setError(null);
    try {
      const res = await postInvestigationDig(q);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : (zh ? "模型暂时不可用，未能生成侦探报告。" : "The model is unavailable right now — no investigation report this time."));
    } finally {
      setBusy(false);
    }
  };

  if (!checked) return <Spinner />;
  if (!canManage) {
    return (
      <div className="page-head">
        <h1>{zh ? "深挖现场" : "The Dig"} <span className="manual-en">{zh ? "THE DIG" : "深挖现场"}</span></h1>
        <div className="page-sub">{zh ? "只对 admin / operator 开放。" : "Admin / operator only."}</div>
        <PermissionDenied action={zh ? "深挖现场仅对 admin / operator 开放（RBAC fail-closed）" : "The Dig is admin / operator only (RBAC fail-closed)"} />
      </div>
    );
  }

  return (
    <div className="page-head">
      <h1>{zh ? "深挖现场" : "The Dig"} <span className="manual-en">{zh ? "THE DIG · 模型问仓库" : "THE DIG · ASK THIS REPO"}</span></h1>
      <div className="page-sub">{zh ? "把问题交给三只只读侦探并行调查；不披甲、不落子、不卖关子。" : "Three readonly investigators examine the repo in parallel. No armouring, no chess moves, no hidden verdicts."}</div>

      <Panel title={zh ? "问什么" : "What to ask"}>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
          <textarea
            className="ui-input"
            rows={2}
            style={{ flex: "1 1 320px", fontFamily: "inherit" }}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={zh ? "例如：这仓库是哪种验证平台？" : "e.g. What kind of verification platform is this?"}
          />
          <Button onClick={ask} disabled={busy} aria-busy={busy}>
            {busy ? (zh ? "侦探中…" : "Digging…") : (zh ? "放侦探出门" : "Send the investigators")}
          </Button>
        </div>
        <p style={{ fontSize: "var(--text-xs)", opacity: 0.72, marginTop: "0.5rem" }}>
          {zh ? "只读并行；三位侦探同一裁判线 · facts 包上限 4 KB；INSUFFICIENT 不会涂绿。" : "Readonly parallel; three diggers on one question; fact pack ≤ 4 KB; INSUFFICIENT is never painted jade."}
        </p>
      </Panel>

      {error && (
        <Panel title={zh ? "侦探报告" : "The Report"}>
          <p role="alert">{error}</p>
        </Panel>
      )}

      {result && (
        <Panel title={zh ? "侦探报告" : "The Report"}>
          <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap", alignItems: "baseline" }}>
            <span className="ui-badge">{result.verdict}</span>
            {typeof result.total_tokens_used === "number" ? (
              <span style={{ fontFamily: "var(--font-mono)" }}>{result.total_tokens_used} tokens</span>
            ) : null}
            {typeof result.generation_time_ms === "number" ? (
              <span style={{ fontFamily: "var(--font-mono)" }}>{Math.round(result.generation_time_ms / 1000)}s</span>
            ) : null}
          </div>
          <p><strong>{zh ? "问题" : "Question"}:</strong> {result.question}</p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "1rem" }}>
            {result.agents.map((a, i) => (
              <div key={i} className="panel-section">
                <h4>{a.name ?? a.role ?? `agent ${i}`}</h4>
                <p style={{ fontFamily: "var(--font-mono)" }}>{a.outcome}{typeof a.tokens === "number" ? ` · ${a.tokens} tokens` : ""}</p>
              </div>
            ))}
          </div>
          <ol style={{ paddingInlineStart: "1.25rem" }}>
            {result.findings.map((f, i) => (
              <li key={i} style={{ marginBottom: "0.5rem" }}>
                <strong>{f.role}</strong> — {f.claim}
              </li>
            ))}
          </ol>
        </Panel>
      )}
    </div>
  );
}
