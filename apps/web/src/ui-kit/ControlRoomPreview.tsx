import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Progress } from "../ui/Progress";
import { StatusDot, type DotStatus } from "../ui/StatusDot";
import { Table, type Column } from "../ui/Table";
import { Timeline, type TimelineEvent } from "../ui/Timeline";

interface CheckRow {
  id: string;
  spec: string;
  status: DotStatus;
  statusLabel: string;
  checkpoints: number;
  duration: number | null;
  verdict: string;
}

const CHECKS: CheckRow[] = [
  { id: "SP-2481", spec: "AUTH-01 邮箱变更认证", status: "success", statusLabel: "完成", checkpoints: 6, duration: 38.2, verdict: "VERIFIED" },
  { id: "SP-2480", spec: "EVT-04 事件幂等", status: "running", statusLabel: "运行中", checkpoints: 4, duration: null, verdict: "RUNNING" },
  { id: "SP-2479", spec: "BROKER-02 重试去重", status: "danger", statusLabel: "失败", checkpoints: 5, duration: 51.7, verdict: "BLOCKED" },
  { id: "SP-2478", spec: "AUTH-02 令牌失效", status: "success", statusLabel: "完成", checkpoints: 6, duration: 29.4, verdict: "VERIFIED" },
  { id: "SP-2477", spec: "EVT-03 时间戳保留", status: "idle", statusLabel: "排队", checkpoints: 6, duration: null, verdict: "QUEUED" },
];

const COLUMNS: Column<CheckRow>[] = [
  { key: "id", header: "ID", width: 84, render: (row) => <span className="ui-kit-num">{row.id}</span> },
  { key: "spec", header: "契约" },
  {
    key: "status",
    header: "状态",
    width: 120,
    render: (row) => <StatusDot status={row.status} label={row.statusLabel} />,
  },
  { key: "checkpoints", header: "检查点", align: "right", sortable: true, render: (row) => <span className="ui-kit-num">{row.checkpoints}</span> },
  {
    key: "duration",
    header: "耗时",
    align: "right",
    sortable: true,
    sortValue: (row) => row.duration ?? -1,
    render: (row) => <span className="ui-kit-num">{row.duration === null ? "—" : row.duration.toFixed(1) + "s"}</span>,
  },
  {
    key: "verdict",
    header: "结论",
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

const PIPELINE: TimelineEvent[] = [
  { id: "intake", title: "intake — 需求接收", description: "解析规格 AUTH-01，提取 6 条契约", time: "14:02:11", status: "success" },
  { id: "contracts", title: "contracts — 契约编译", description: "6/6 契约可验证，无编译错误", time: "14:02:19", status: "success" },
  { id: "differential", title: "differential — 差分执行", description: "base vs head-v1 · JUnit 回归运行中", time: "14:02:47", status: "running" },
  { id: "review", title: "review — 审查庭复核", description: "等待差分证据汇总", time: "—", status: "idle" },
  { id: "certificate", title: "certificate — 合并证书", description: "SHA-256 签名", time: "—", status: "idle" },
];

export function ControlRoomPreview(): JSX.Element {
  return (
    <div className="prev-root">
      <div className="prev-topbar">
        <span className="prev-logo" aria-hidden="true">
          SP
        </span>
        <span className="prev-name">SpecProof Control Room</span>
        <span className="prev-crumb">verify · specproof/demo — base → head-v1</span>
        <span className="prev-spacer" />
        <StatusDot status="running" label="pipeline 运行中" />
        <Badge tone="danger">BLOCKER ×1</Badge>
      </div>

      <div className="prev-hero">
        <div className="prev-title">
          差分验证 · <span className="ui-text-gradient">AUTH-01 邮箱变更认证</span>
        </div>
        <div className="prev-sub">
          静态源码差分 + 运行时 JUnit 双重证据 · 独立于变更作者的 AI 审查 · 合并前拦截回归
        </div>
        <div className="prev-actions">
          <Button variant="primary">查看完整报告</Button>
          <Button variant="secondary">回放 Capsule</Button>
          <Button variant="ghost">生成证书</Button>
        </div>
        <div className="prev-metrics">
          <div className="prev-metric">
            <div className="prev-metric-label">
              <StatusDot status="success" size="sm" /> 今日验证
            </div>
            <div className="prev-metric-value">42</div>
            <div className="prev-metric-delta prev-delta-up">+12 vs 昨日</div>
          </div>
          <div className="prev-metric">
            <div className="prev-metric-label">
              <StatusDot status="danger" size="sm" /> 拦截回归
            </div>
            <div className="prev-metric-value">9</div>
            <div className="prev-metric-delta prev-delta-up">+3 新增拦截</div>
          </div>
          <div className="prev-metric">
            <div className="prev-metric-label">
              <StatusDot status="info" size="sm" /> 平均验证时长
            </div>
            <div className="prev-metric-value">4m 12s</div>
            <div className="prev-metric-delta prev-delta-up">−38s 更快</div>
          </div>
          <div className="prev-metric">
            <div className="prev-metric-label">
              <StatusDot status="warning" size="sm" /> 契约覆盖
            </div>
            <div className="prev-metric-value">96.4%</div>
            <div className="prev-metric-delta prev-delta-up">+2.1% 覆盖提升</div>
          </div>
        </div>
      </div>

      <div className="prev-body">
        <div className="prev-card">
          <div className="prev-card-title">
            <span>最近验证 Recent checks</span>
            <Badge tone="neutral">LIVE</Badge>
          </div>
          <Table columns={COLUMNS} rows={CHECKS} rowKey={(row) => row.id} dense />
        </div>
        <div className="prev-card">
          <div className="prev-card-title">
            <span>执行管道 Pipeline</span>
          </div>
          <Timeline events={PIPELINE} />
          <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 12 }}>
            <Progress label="门禁通过率" value={98} tone="success" showValue />
            <Progress label="证据覆盖" value={86} showValue />
            <Progress label="回归检测" value={74} tone="warning" showValue />
          </div>
        </div>
      </div>
    </div>
  );
}
