import { useEffect, useState } from "react";
import { apiGet, type DashboardData } from "../api";
import { Button, ErrorBox, Panel, StatusPill, fmtTime, shortId, CountUp, AreaChart, DonutMeter } from "../ui";
import { describeDegradedReason } from "../ui/errorHints";
import { ProductIcon } from "../ui/ProductIcon";
import { useI18n } from "../i18n";
import { DASHBOARD_BY_LOCALE } from "./dashboard.copy";

export default function Dashboard() {
  const { locale } = useI18n();
  const c = DASHBOARD_BY_LOCALE[locale];
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    apiGet<DashboardData>("/api/v1/dashboard").then(value => { if (alive) setData(value); }).catch(reason => { if (alive) setError(reason as Error); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [refresh]);
  const hasData = data !== null && !data.degraded;
  const stats = hasData ? data.jobs.by_status : {};
  const metricValues = [
    hasData ? data.jobs.total : undefined,
    hasData ? stats.VERIFIED || 0 : undefined,
    hasData ? stats.BLOCKED || 0 : undefined,
    hasData ? (stats.RUNNING || 0) + (stats.QUEUED || 0) : undefined,
  ];
  const metricTones = ["neutral", "success", "warning", "accent"];
  const metricIcons = ["verify", "shield", "health", "chart"] as const;
  const metrics = c.metric.map((metric, index) => ({
    label: metric.label,
    value: metricValues[index],
    hint: metric.hint,
    icon: metricIcons[index],
    tone: metricTones[index],
  }));
  const recent = data?.recent_jobs || [];
  const timeline = data?.timeline_24h || [];
  const max = Math.max(1, ...timeline.map(hour => hour.count));
  const needsAttention = (stats.BLOCKED || 0) + (stats.FAILED || 0) + (stats.ERROR || 0);

  const areaData = timeline.map(hour => ({
    label: hour.hour.slice(11, 16),
    value: hour.count,
    meta: hour.failed ? c.failedSuffix(hour.failed) : undefined,
  }));
  const JOB_STATUS_LABEL = c.statusJob;
  const statusColor: Record<string, string> = {
    VERIFIED: "var(--success)", BLOCKED: "var(--warning)", RUNNING: "var(--accent-500)",
    QUEUED: "var(--accent-400)", FAILED: "var(--danger)", ERROR: "var(--danger)",
    CANCELLED: "var(--color-text-3)", PENDING: "var(--color-text-3)",
  };
  const donutSegments = hasData
    ? Object.entries(data.jobs.by_status)
        .map(([k, v]) => ({ label: JOB_STATUS_LABEL[k] ?? k, value: v, color: statusColor[k] ?? "var(--color-text-3)" }))
        .filter(s => s.value > 0)
    : [];

  return <div className="dashboard product-page">
    <div className="product-page-heading"><div><div className="eyebrow">{c.eyebrow}</div><h1>{c.h1}<span className="heading-dot">{c.h1Dot}</span></h1><p>{c.lead}</p></div><a className="btn btn-primary" href="#/jobs/new"><ProductIcon name="plus" size={17} />{c.newButton}</a></div>

    <section className="welcome-banner" aria-label={c.welcomeAria}><div className="welcome-copy"><span className="welcome-kicker"><span className="tiny-dot" /> {c.welcomeKicker}</span><h2>{c.welcomeH1[0]}<br />{c.welcomeH1[1]}</h2><p>{c.welcomeP[0]}<br className="desktop-break" />{c.welcomeP[1]}</p><a href="#/guide">{c.welcomeGuideLink}<ProductIcon name="arrow" size={16} /></a></div><div className="proof-diagram" aria-label={c.welcomeAria}><div className="diagram-label">{c.diagramLabel}</div><div className="diagram-flow"><div className="diagram-node"><ProductIcon name="contracts" size={25} /><strong>{c.diagramNodeContracts.strong}</strong><small>{c.diagramNodeContracts.small}</small></div><span className="diagram-line" /><div className="diagram-core"><ProductIcon name="shield" size={34} /><strong>{c.diagramCore}</strong></div><span className="diagram-line" /><div className="diagram-node"><ProductIcon name="verify" size={25} /><strong>{c.diagramNodeVerify.strong}</strong><small>{c.diagramNodeVerify.small}</small></div></div><div className="diagram-caption"><span>{c.diagramCaption[0]}</span><span>{c.diagramCaption[1]}</span><span>{c.diagramCaption[2]}</span></div></div></section>

    <section className="quickstart" aria-label={c.quickstartAria}>
      <div className="section-heading"><h2>{c.quickstartTitle}</h2><span>{c.quickstartHint}</span></div>
      <div className="quickstart-grid">{c.quickstart.map(item => <a className="quickstart-card" href={item.href} key={item.step}><span className="quickstart-step">{item.step}</span><strong>{item.title}</strong><p>{item.text}</p><span className="quickstart-cta">{item.cta} <span aria-hidden="true">→</span></span></a>)}</div>
    </section>

    <div className="section-heading"><h2>{c.actionsTitle}</h2><span>{c.actionsHint}</span></div>
    <div className="quick-actions">{c.actions.map((action, index) => <a className="quick-action" href={action.href} key={action.href}><div className="quick-action-top"><span className={"action-icon action-icon-" + index}><ProductIcon name={action.icon} size={23} /></span><span className="action-number">0{index + 1}</span></div><h3>{action.title}</h3><p>{action.text}</p><span className="action-link">{action.label}<ProductIcon name="arrow" size={16} /></span></a>)}</div>

    <div className="section-heading"><h2>{c.metricsTitle}</h2><Button variant="ghost" size="sm" loading={loading} onClick={() => setRefresh(value => value + 1)}>{c.refresh}</Button></div>
    {error && <div className="dashboard-error"><ErrorBox error={error} /><p>{c.errorLead} <a href="#/health">{locale === "zh" ? "服务状态" : "Service status"}</a></p></div>}
    {data?.degraded && <div className="degraded" role="status"><strong>{c.degradedTitle}</strong><span>{c.degradedTrail}</span><details><summary>{c.degradedRawSummary}</summary><ul>{data.degraded_reasons.map(reason => <li key={reason} title={reason}>{describeDegradedReason(reason)}</li>)}</ul></details></div>}
    <div className="metrics-grid" aria-busy={loading}>{metrics.map(metric => <div className={"metric-card metric-" + metric.tone} key={metric.label}><div className="metric-top"><span>{metric.label}</span><ProductIcon name={metric.icon} size={18} /></div><strong>{loading && !data ? <span className="metric-skeleton" /> : metric.value === undefined ? "—" : <CountUp value={metric.value} className="metric-count" />}</strong><small>{metric.hint}</small></div>)}</div>

    <div className="insight-grid">
      <Panel title={c.timelineTitle} right={<span className="muted">{data?.timeline_timezone}</span>}>
        <AreaChart data={areaData} ariaLabel={c.timelineAria} formatValue={(n) => String(n)} emptyHint={c.timelineEmpty} />
      </Panel>
      <Panel title={c.statusTitle} right={hasData ? <span className="muted">{c.statusTotalBefore}{data.jobs.total} {c.statusCenterLabel}</span> : undefined}>
        <DonutMeter segments={donutSegments} centerValue={hasData ? data.jobs.total : undefined} centerLabel={c.statusCenterLabel} ariaLabel={c.statusAria} emptyHint={c.statusEmpty} />
      </Panel>
    </div>

    <div className="dashboard-bottom"><div className="recent-panel"><Panel title={c.recentTitle} right={<a href="#/jobs">{c.recentViewAll}<span aria-hidden="true">→</span></a>}>
      {!data && loading ? <div className="product-empty" role="status">{c.loadingRecords}</div> : recent.length === 0 ? <div className="product-empty"><span className="empty-illustration"><ProductIcon name="verify" size={32} /></span><h3>{error ? c.errorTitle : c.emptyTitle}</h3><p>{error ? c.errorCopy : c.emptyCopy}</p><a className="btn" href={error ? "#/health" : "#/jobs/new"}>{error ? c.errorCta : c.emptyCta}<ProductIcon name="arrow" size={15} /></a></div> : <div className="table-scroll"><table className="data"><thead><tr><th>{c.thRepo}</th><th>{c.thStatus}</th><th>{c.thCreated}</th><th><span className="sr-only">{c.thView}</span></th></tr></thead><tbody>{recent.map(job => <tr key={job.id}><td><a className="job-title" href={"#/jobs/" + encodeURIComponent(job.id)}>{job.repo_path?.replace(/\\/g, "/").split("/").filter(Boolean).pop() || shortId(job.id)}</a>{job.is_demo ? <span className="demo-label">{c.demoLabel}</span> : null}<div className="job-refs">{job.base_ref || "—"}<span> → </span>{job.head_ref || "—"}</div></td><td><StatusPill status={job.status || "UNKNOWN"} /></td><td className="muted">{fmtTime(job.created_at)}</td><td><a className="icon-button" href={"#/jobs/" + encodeURIComponent(job.id)} aria-label={c.ariaViewJob + job.id}><ProductIcon name="arrow" size={16} /></a></td></tr>)}</tbody></table></div>}
    </Panel><div className="delivery-note"><ProductIcon name="shield" size={17} /><span>{c.recentNote}</span></div></div>
    <aside className="activity-panel"><Panel title={c.activityTitle} right={<span className="muted">{c.activityTotal}</span>}><div className="activity-total"><strong>{hasData ? timeline.reduce((sum, hour) => sum + hour.count, 0) : "—"}</strong><span>{c.activityUnit}</span></div>{timeline.some(hour => hour.count > 0) ? <><div className="activity-chart" role="img" aria-label={c.timelineAriaLabel + " · " + data?.timeline_timezone}>{timeline.map(hour => <div className="activity-chart-track" key={hour.hour} title={hour.hour + " · " + hour.count + " · " + c.failedSuffix(hour.failed)}><span style={{ height: Math.max(3, (hour.count / max) * 76) }} className={hour.failed ? "activity-bar-failed" : ""} /></div>)}</div><div className="chart-axis"><span>{timeline[0]?.hour.slice(11, 16)}</span><span>{data?.timeline_timezone}</span><span>{timeline[timeline.length - 1]?.hour.slice(11, 16)}</span></div></> : <div className="activity-no-data">{hasData ? c.activityEmpty : c.activityNoData}</div>}<div className="activity-summary"><span className={needsAttention ? "attention-dot" : "tiny-dot"} /><div><strong>{hasData ? (needsAttention ? c.summaryNeedsAttention(needsAttention) : c.activityCalm) : c.pendingChecks}</strong><p>{needsAttention ? c.attentionCopy : c.calmCopy}</p></div></div><a className="activity-link" href="#/jobs">{c.activityViewJobs}<ProductIcon name="arrow" size={16} /></a></Panel></aside></div>
  </div>;
}
