import { useEffect, useState } from "react";
import { PermissionDenied } from "../identity/PermissionDenied";
import { useIdentityAccess } from "../identity/useIdentityAccess";
import { useI18n } from "../i18n";
import { Panel, Spinner, ErrorBox, Button, StatCard, Empty } from "../ui";
import { ProductIcon } from "../ui/ProductIcon";
import {
  fetchRunbookAlerts,
  postRunbookTriage,
  type RunbookTriage,
} from "../api";

export default function Runbook(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const { checked, canManage } = useIdentityAccess();
  const [alerts, setAlerts] = useState<string[]>([]);
  const [alertsError, setAlertsError] = useState<string | null>(null);
  const [alertsLoaded, setAlertsLoaded] = useState(false);
  const [selected, setSelected] = useState<string>("");
  const [state, setState] = useState<"idle" | "loading" | "error" | "done">("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RunbookTriage | null>(null);

  useEffect(() => {
    if (!canManage) return;
    let alive = true;
    fetchRunbookAlerts()
      .then((v) => {
        if (!alive) return;
        setAlerts(v.alerts);
        setAlertsLoaded(true);
        if (v.alerts.length > 0) setSelected(v.alerts[0]);
      })
      .catch((exc: unknown) => {
        if (!alive) return;
        setAlertsError(exc instanceof Error ? exc.message : String(exc));
        setAlertsLoaded(true);
      });
    return () => {
      alive = false;
    };
  }, [canManage]);

  const submit = async (): Promise<void> => {
    if (!selected) return;
    setState("loading");
    setError(null);
    setResult(null);
    try {
      const out = await postRunbookTriage(selected);
      setResult(out);
      setState("done");
    } catch (exc) {
      setState("error");
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  };

  if (!checked) return <Spinner />;
  if (!canManage) {
    const perm = zh ? "值班手册只对 admin / operator 开放" : "The runbook is admin / operator only";
    return (
      <div className="page-head">
        <h1>{perm} <span className="manual-en">{zh ? "VALUEBOOK" : "RUNBOOK"}</span></h1>
        <PermissionDenied action={zh ? "值班手册仅对 admin / operator 开放（RBAC fail-closed）" : "The runbook is admin / operator only (RBAC fail-closed)"} />
      </div>
    );
  }

  const L = (a: string, b: string): string => (zh ? a : b);

  return (
    <div className="runbook-page">
      <header className="page-mast">
        <ProductIcon name="shield" size={28} />
        <div>
          <p className="page-kicker">{L("值班手册 · 单机版", "RUNBOOK · SINGLE-HOST EDITION")}</p>
          <h1>{L("告警一响，模型先读自己仓库", "The alert fires; the model reads this repo first")}</h1>
          <p className="page-sub">
            {L(
              "三只只读证据兄妹并发回答：这条告警是什么、先看什么、仓库里的事实是否支持。永远不涂绿，INCONCLUSIVE 是答案。",
              "Three readonly investigators answer: what this alert means, what to check first, and whether the repo's facts support the reading. Never painted green — INCONCLUSIVE is an answer.",
            )}
          </p>
        </div>
      </header>

      <Panel title={L("条例 · 一句", "The one-line rule")}>
        <p className="runbook-note">
          {L(
            "admin/operator 专属。所有结论来自仓库内事实；模型不改告警、不改判词；结论与仓库事实之间的距离写在脸上。",
            "Admin/operator only. Everything here comes from repo facts; the model edits neither alerts nor verdicts; the gap between claim and evidence is written on the face of the answer.",
          )}
        </p>
      </Panel>

      <Panel title={L("选一条告警", "Pick an alert")}>
        {alertsError ? (
          <ErrorBox error={alertsError} />
        ) : !alertsLoaded ? (
          <Spinner />
        ) : alerts.length === 0 ? (
          <Empty text={L("这条警报树里还没有东西——先让规则落地。", "No alert is deployed yet — land the rules first.")} />
        ) : (
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              className="select"
              aria-label={L("选择告警", "Alert")}
              style={{ minWidth: 260 }}
            >
              {alerts.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
            <Button onClick={() => void submit()} disabled={state === "loading" || !selected}>
              {state === "loading" ? L("三只兄妹并发中…", "The three investigators are running…") : L("三只兄妹并发问", "Run the investigation")}
            </Button>
          </div>
        )}
      </Panel>

      {state === "error" && error ? (
        <Panel title={L("模型不可用", "The model could not be reached")}>
          <ErrorBox error={error} />
          <p className="runbook-note">
            {L(
              "503 一律当场上报。模型不凭空给出处置建议。",
              "A 503 is reported as-is. No fabricated triage is ever handed to you.",
            )}
          </p>
        </Panel>
      ) : null}

      {result ? (
        <Panel title={L("兄妹说了什么", "What the siblings saw")}>
          <div className="stat-grid" role="group" aria-label={L("判词", "Verdict")}>
            <StatCard label={L("告警", "Alert")} value={result.alert} />
            <StatCard
              label={L("判词", "Verdict")}
              value={result.verdict}
              tone={result.verdict === "CONFIRMED" ? "ok" : "warn"}
            />
            <StatCard label="Tokens" value={String(result.total_tokens_used ?? 0)} />
            <StatCard label={L("缓存", "Cached")} value={String(result.cached)} />
          </div>
          <ol className="runbook-findings">
            {result.findings.map((f, index) => (
              <li key={index}>
                <strong>{f.role}</strong>
                <p>{f.claim}</p>
                <p className="runbook-confidence">
                  {L("置信", "Confidence")} {f.confidence}
                  {" · "}
                  {L("证据", "Evidence")} {f.evidence}
                </p>
              </li>
            ))}
          </ol>
        </Panel>
      ) : null}
    </div>
  );
}
