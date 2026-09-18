import { useEffect, useState } from "react";
import { apiGet, type DashboardData } from "../api";
import { Button, ErrorBox, Panel, StatusPill, fmtTime, shortId } from "../ui";
import { ProductIcon, type ProductIconName } from "../ui/ProductIcon";

const ACTIONS: { href: string; icon: ProductIconName; title: string; text: string; label: string }[] = [
  { href: "#/jobs/new", icon: "verify", title: "验收一次代码变更", text: "已有代码？对照需求检查变更，找出回归与遗漏。", label: "开始验收" },
  { href: "#/agent/new", icon: "agent", title: "让 AI 协助开发", text: "描述任务，审阅执行计划，再交给 AI 完成开发。", label: "创建开发任务" },
  { href: "#/guide", icon: "guide", title: "先了解它怎么工作", text: "跟着一个权限校验的例子，读懂验收结果和证据。", label: "查看上手指南" },
];

// 新手上路清单：把"这个产品能干嘛"翻译成 4 个可点的动作。
const QUICKSTART: { step: string; title: string; text: string; href: string; cta: string }[] = [
  { step: "01", title: "看一条演示结果", text: "标有“演示”的任务是预置示例，点开就能看到结论、风险与证据长什么样。", href: "#/jobs", cta: "打开验收列表" },
  { step: "02", title: "跑一次真实验收", text: "新建验收页可一键填入演示案例（含故意引入的权限回归），提交后观察它如何被拦截。", href: "#/jobs/new", cta: "用演示案例验收" },
  { step: "03", title: "让 AI 修一个 Bug", text: "AI 开发向导内置示例需求，一键填充后生成计划，你批准前不会改任何代码。", href: "#/agent/new", cta: "试试 AI 开发" },
  { step: "04", title: "接上你的模型", text: "在模型连接里填入服务商信息并测试连接，之后任务由真实模型驱动。", href: "#/settings", cta: "配置模型" },
];

export default function Dashboard() {
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
  const metrics: { label: string; value: number | undefined; hint: string; icon: ProductIconName; tone: string }[] = [
    { label: "累计验收", value: hasData ? data.jobs.total : undefined, hint: "工作空间内的变更记录", icon: "verify", tone: "neutral" },
    { label: "验收通过", value: hasData ? stats.VERIFIED || 0 : undefined, hint: "已通过本次执行的检查", icon: "shield", tone: "success" },
    { label: "发现风险", value: hasData ? stats.BLOCKED || 0 : undefined, hint: "需根据证据修复后再提交", icon: "health", tone: "warning" },
    { label: "正在处理", value: hasData ? (stats.RUNNING || 0) + (stats.QUEUED || 0) : undefined, hint: "排队或执行中的验收", icon: "chart", tone: "accent" },
  ];
  const recent = data?.recent_jobs || [];
  const timeline = data?.timeline_24h || [];
  const max = Math.max(1, ...timeline.map(hour => hour.count));
  const needsAttention = (stats.BLOCKED || 0) + (stats.FAILED || 0) + (stats.ERROR || 0);

  return <div className="dashboard product-page">
    <div className="product-page-heading"><div><div className="eyebrow">YOUR DELIVERY WORKSPACE</div><h1>每一次交付，都更有把握<span className="heading-dot">.</span></h1><p>从需求到证据，清楚知道这次代码变更是否符合预期。</p></div><a className="btn btn-primary" href="#/jobs/new"><ProductIcon name="plus" size={17} />新建验收</a></div>

    <section className="welcome-banner" aria-label="SpecProof 是什么"><div className="welcome-copy"><span className="welcome-kicker"><span className="tiny-dot" /> 独立验收 · 可追溯证据</span><h2>代码写好了，<br />让结果经得起验证。</h2><p>SpecProof 对比变更前后的代码，检查是否满足你的需求，<br className="desktop-break" />并把发现的问题、覆盖情况和验证证据放在一起。</p><a href="#/guide">了解 SpecProof 如何验收 <ProductIcon name="arrow" size={16} /></a></div><div className="proof-diagram" aria-label="需求经过独立验收，生成结论与证据"><div className="diagram-label">FROM CHANGE TO CONFIDENCE</div><div className="diagram-flow"><div className="diagram-node"><ProductIcon name="contracts" size={25} /><strong>需求与变更</strong><small>你希望实现什么</small></div><span className="diagram-line" /><div className="diagram-core"><ProductIcon name="shield" size={34} /><strong>独立验收</strong></div><span className="diagram-line" /><div className="diagram-node"><ProductIcon name="verify" size={25} /><strong>结论与证据</strong><small>实际验证了什么</small></div></div><div className="diagram-caption"><span>需求检查</span><span>版本对比</span><span>问题定位</span></div></div></section>

    <section className="quickstart" aria-label="5 分钟快速上手">
      <div className="section-heading"><h2>5 分钟快速上手</h2><span>按顺序体验一遍，就知道 SpecProof 能为你做什么</span></div>
      <div className="quickstart-grid">{QUICKSTART.map(item => <a className="quickstart-card" href={item.href} key={item.step}><span className="quickstart-step">{item.step}</span><strong>{item.title}</strong><p>{item.text}</p><span className="quickstart-cta">{item.cta} <span aria-hidden="true">→</span></span></a>)}</div>
    </section>

    <div className="section-heading"><h2>开始你的下一次交付</h2><span>选择适合当前阶段的工作方式</span></div>
    <div className="quick-actions">{ACTIONS.map((action, index) => <a className="quick-action" href={action.href} key={action.href}><div className="quick-action-top"><span className={"action-icon action-icon-" + index}><ProductIcon name={action.icon} size={23} /></span><span className="action-number">0{index + 1}</span></div><h3>{action.title}</h3><p>{action.text}</p><span className="action-link">{action.label}<ProductIcon name="arrow" size={16} /></span></a>)}</div>

    <div className="section-heading"><h2>验收概况</h2><Button variant="ghost" size="sm" loading={loading} onClick={() => setRefresh(value => value + 1)}>刷新数据</Button></div>
    {error && <div className="dashboard-error"><ErrorBox error={error} /><p>暂时无法读取验收数据。可以重试，或到 <a href="#/health">服务状态</a> 查看连接情况。</p></div>}
    {data?.degraded && <div className="degraded" role="status"><strong>部分数据暂不可用</strong><span> · 已显示能够读取的结果。</span><details><summary>查看原因</summary><ul>{data.degraded_reasons.map(reason => <li key={reason}>{reason}</li>)}</ul></details></div>}
    <div className="metrics-grid" aria-busy={loading}>{metrics.map(metric => <div className={"metric-card metric-" + metric.tone} key={metric.label}><div className="metric-top"><span>{metric.label}</span><ProductIcon name={metric.icon} size={18} /></div><strong>{loading && !data ? <span className="metric-skeleton" /> : metric.value?.toLocaleString() ?? "—"}</strong><small>{metric.hint}</small></div>)}</div>

    <div className="dashboard-bottom"><div className="recent-panel"><Panel title="最近验收" right={<a href="#/jobs">查看全部 <span aria-hidden="true">↗</span></a>}>
      {!data && loading ? <div className="product-empty" role="status">正在读取验收记录…</div> : recent.length === 0 ? <div className="product-empty"><span className="empty-illustration"><ProductIcon name="verify" size={32} /></span><h3>{error ? "验收记录暂不可用" : "把第一次变更，交给事实验证"}</h3><p>{error ? "服务恢复后，验收记录会显示在这里。" : "提交代码仓库、前后版本和需求文件，即可开始。"}</p><a className="btn" href={error ? "#/health" : "#/jobs/new"}>{error ? "检查服务状态" : "创建第一条验收"}<ProductIcon name="arrow" size={15} /></a></div> : <div className="table-scroll"><table className="data"><thead><tr><th>仓库 / 版本</th><th>验收结果</th><th>提交时间</th><th><span className="sr-only">查看详情</span></th></tr></thead><tbody>{recent.map(job => <tr key={job.id}><td><a className="job-title" href={"#/jobs/" + encodeURIComponent(job.id)}>{job.repo_path?.replace(/\\/g, "/").split("/").filter(Boolean).pop() || shortId(job.id)}</a>{!!job.is_demo && <span className="demo-label">演示</span>}<div className="job-refs">{job.base_ref || "—"}<span> → </span>{job.head_ref || "—"}</div></td><td><StatusPill status={job.status || "UNKNOWN"} /></td><td className="muted">{fmtTime(job.created_at)}</td><td><a className="icon-button" href={"#/jobs/" + encodeURIComponent(job.id)} aria-label={"查看验收 " + job.id}><ProductIcon name="arrow" size={16} /></a></td></tr>)}</tbody></table></div>}
    </Panel><div className="delivery-note"><ProductIcon name="shield" size={17} /><span>标有“演示”的记录为示例数据。真实验收通过仅覆盖本次执行的检查。</span></div></div>
    <aside className="activity-panel"><Panel title="交付动态" right={<span className="muted">近 24 小时</span>}><div className="activity-total"><strong>{hasData ? timeline.reduce((sum, hour) => sum + hour.count, 0) : "—"}</strong><span>次验收提交</span></div>{timeline.some(hour => hour.count > 0) ? <><div className="activity-chart" role="img" aria-label={"近 24 小时验收数量，时区 " + data?.timeline_timezone}>{timeline.map(hour => <div className="activity-chart-track" key={hour.hour} title={hour.hour + " · " + hour.count + " 次，失败 " + hour.failed + " 次"}><span style={{ height: Math.max(3, (hour.count / max) * 76) }} className={hour.failed ? "activity-bar-failed" : ""} /></div>)}</div><div className="chart-axis"><span>{timeline[0]?.hour.slice(11, 16)}</span><span>{data?.timeline_timezone}</span><span>{timeline[timeline.length - 1]?.hour.slice(11, 16)}</span></div></> : <div className="activity-no-data">{hasData ? "近 24 小时暂无验收活动" : "连接服务后查看交付动态"}</div>}<div className="activity-summary"><span className={needsAttention ? "attention-dot" : "tiny-dot"} /><div><strong>{hasData ? (needsAttention ? needsAttention + " 条验收需要关注" : "暂没有待处理的风险") : "等待验收数据"}</strong><p>{needsAttention ? "查看拦截原因，或重试执行失败的任务。" : "新的验收进展会记录在任务详情中。"}</p></div></div><a className="activity-link" href="#/jobs">进入验收列表 <ProductIcon name="arrow" size={16} /></a></Panel></aside></div>
  </div>;
}
