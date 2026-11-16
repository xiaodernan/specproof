import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Progress } from "../ui/Progress";
import { StatusDot, type DotStatus } from "../ui/StatusDot";
import { Table, type Column } from "../ui/Table";
import { Timeline, type TimelineEvent } from "../ui/Timeline";
import { storedLocale } from "../i18n/strings";
const isZh = (): boolean => storedLocale() === "zh";
const L = (zh: string, en: string): string => (isZh() ? zh : en);

interface CheckRow {
  id: string;
  spec: string;
  status: DotStatus;
  statusLabel: string;
  checkpoints: number;
  duration: number | null;
  verdict: string;
}

const buildChecks = (): CheckRow[] => [
  { id: "SP-2481", spec: L("AUTH-01 邮箱变更认证", "AUTH-01 email-change auth"), status: "success", statusLabel: L("完成", "Done"), checkpoints: 6, duration: 38.2, verdict: "VERIFIED" },
  { id: "SP-2480", spec: L("EVT-04 事件幂等", "EVT-04 event idempotency"), status: "running", statusLabel: L("运行中", "Running"), checkpoints: 4, duration: null, verdict: "RUNNING" },
  { id: "SP-2479", spec: L("BROKER-02 重试去重", "BROKER-02 retry dedup"), status: "danger", statusLabel: L("失败", "Failed"), checkpoints: 5, duration: 51.7, verdict: "BLOCKED" },
  { id: "SP-2478", spec: L("AUTH-02 令牌失效", "AUTH-02 token revocation"), status: "success", statusLabel: L("完成", "Done"), checkpoints: 6, duration: 29.4, verdict: "VERIFIED" },
  { id: "SP-2477", spec: L("EVT-03 时间戳保留", "EVT-03 timestamp retention"), status: "idle", statusLabel: L("排队", "Queued"), checkpoints: 6, duration: null, verdict: "QUEUED" },
];

const buildColumns = (): Column<CheckRow>[] => [
  { key: "id", header: "ID", width: 84, render: (row) => <span className="ui-kit-num">{row.id}</span> },
  { key: "spec", header: L("契约", "Contract") },
  {
    key: "status",
    header: L("状态", "Status"),
    width: 120,
    render: (row) => <StatusDot status={row.status} label={row.statusLabel} />,
  },
  { key: "checkpoints", header: L("检查点", "Checkpoints"), align: "right", sortable: true, render: (row) => <span className="ui-kit-num">{row.checkpoints}</span> },
  {
    key: "duration",
    header: L("耗时", "Time"),
    align: "right",
    sortable: true,
    sortValue: (row) => row.duration ?? -1,
    render: (row) => <span className="ui-kit-num">{row.duration === null ? "—" : row.duration.toFixed(1) + "s"}</span>,
  },
  {
    key: "verdict",
    header: L("结论", "Verdict"),
    width: 100,
    render: (row) => {
      const tone =
        row.verdict === "VERIFIED"
          ? "success"
          : row.verdict === "BLOCKED"
          ? "danger"
          : row.verdict === "RUNNING"
          ? "info"
          : "neutral";
      return <Badge tone={tone}>{row.verdict}</Badge>;
    },
  },
];

const buildPipeline = (): TimelineEvent[] => [
  { id: "intake", title: L("intake — 需求接收", "intake — spec accepted"), description: L("解析规格 AUTH-01，提取 6 条契约", "Parsed spec AUTH-01; 6 contracts extracted"), time: "14:02:11", status: "success" },
  { id: "contracts", title: L("contracts — 契约编译", "contracts — compile"), description: L("6/6 契约可验证，无编译错误", "6/6 contracts verifiable, no compile errors"), time: "14:02:19", status: "success" },
  { id: "differential", title: L("differential — 差分执行", "differential — execution"), description: L("base vs head-v1 · JUnit 回归运行中", "base vs head-v1 · JUnit regression running"), time: "14:02:47", status: "running" },
  { id: "review", title: L("review — 审查庭复核", "review — court review"), description: L("等待差分证据汇总", "Waiting for the differential evidence to land"), time: "—", status: "idle" },
  { id: "certificate", title: L("certificate — 合并证书", "certificate — merge"), description: L("SHA-256 签名", "SHA-256 signature"), time: "—", status: "idle" },
];

export function ControlRoomPreview(): JSX.Element {
  const checks = buildChecks();
  const columns = buildColumns();
  const pipeline = buildPipeline();
  return (
    <div className="prev-root">
      <div className="prev-topbar">
        <span className="prev-logo" aria-hidden="true">
          SP
        </span>
        <span className="prev-name">SpecProof Control Room</span>
        <span className="prev-crumb">verify · specproof/demo — base → head-v1</span>
        <span className="prev-spacer" />
        <StatusDot status="running" label={L("pipeline 运行中", "pipeline running")} />
        <Badge tone="danger">BLOCKER ×1</Badge>
      </div>

      <div className="prev-hero">
        <div className="prev-title">
          {L("差分验证", "Differential verification")} · <span className="ui-text-gradient">AUTH-01 · {L("邮箱变更认证", "email-change auth")}</span>
        </div>
        <div className="prev-sub">
          {L("静态源码差分 + 运行时 JUnit 双重证据 · 独立于变更作者的 AI 审查 · 合并前拦截回归", "Static source diff + runtime JUnit, double-witnessed · AI review independent of the change author · regressions blocked pre-merge")}
        </div>
        <div className="prev-actions">
          <Button variant="primary">{L("查看完整报告", "Open the full report")}</Button>
          <Button variant="secondary">{L("回放 Capsule", "Replay the capsule")}</Button>
          <Button variant="ghost">{L("生成证书", "Issue the certificate")}</Button>
        </div>
        <div className="prev-metrics">
          <div className="prev-metric">
            <div className="prev-metric-label">
              <StatusDot status="success" size="sm" /> {L("今日验证", "Verified today")}
            </div>
            <div className="prev-metric-value">42</div>
            <div className="prev-metric-delta prev-delta-up">+12 {L("vs 昨日", "vs yesterday")}</div>
          </div>
          <div className="prev-metric">
            <div className="prev-metric-label">
              <StatusDot status="danger" size="sm" /> {L("拦截回归", "Regressions blocked")}
            </div>
            <div className="prev-metric-value">9</div>
            <div className="prev-metric-delta prev-delta-up">+3 {L("新增拦截", "new blocks")}</div>
          </div>
          <div className="prev-metric">
            <div className="prev-metric-label">
              <StatusDot status="info" size="sm" /> {L("平均验证时长", "Mean verify time")}
            </div>
            <div className="prev-metric-value">4m 12s</div>
            <div className="prev-metric-delta prev-delta-up">−38s {L("更快", "faster")}</div>
          </div>
          <div className="prev-metric">
            <div className="prev-metric-label">
              <StatusDot status="warning" size="sm" /> {L("契约覆盖", "Contract coverage")}
            </div>
            <div className="prev-metric-value">96.4%</div>
            <div className="prev-metric-delta prev-delta-up">+2.1% {L("覆盖提升", "coverage")}</div>
          </div>
        </div>
      </div>

      <div className="prev-body">
        <div className="prev-card">
          <div className="prev-card-title">
            <span>{L("最近验证", "Recent checks")} · Recent checks</span>
            <Badge tone="neutral">LIVE</Badge>
          </div>
          <Table columns={columns} rows={checks} rowKey={(row) => row.id} dense />
        </div>
        <div className="prev-card">
          <div className="prev-card-title">
            <span>{L("执行管道", "Pipeline")} · Pipeline</span>
          </div>
          <Timeline events={pipeline} />
          <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 12 }}>
            <Progress label={L("门禁通过率", "Gates passed")} value={98} tone="success" showValue />
            <Progress label={L("证据覆盖", "Evidence coverage")} value={86} showValue />
            <Progress label={L("回归检测", "Regression checks")} value={74} tone="warning" showValue />
          </div>
        </div>
      </div>
    </div>
  );
}
