import { Component, ReactNode } from "react";

// Shared presentational components - dark industrial theme, no external UI lib.

export function StatusPill(props: { status: string }) {
  const s = (props.status || "UNKNOWN").toUpperCase();
  const cls =
    s === "VERIFIED"
      ? "pill-ok"
      : s === "BLOCKED" || s === "FAILED" || s === "ERROR"
      ? "pill-bad"
      : s === "RUNNING" || s === "QUEUED" || s === "PENDING" || s === "WAITING_FOR_PROVIDER"
      ? "pill-run"
      : "pill-mute";
  return <span className={"pill " + cls}>{s}</span>;
}

export function Panel(props: { title: string; children?: ReactNode; right?: ReactNode }) {
  return (
    <section className="panel">
      <header className="panel-head">
        <h2>{props.title}</h2>
        {props.right ? <div className="panel-right">{props.right}</div> : null}
      </header>
      <div className="panel-body">{props.children}</div>
    </section>
  );
}

export function StatCard(props: {
  label: string;
  value: ReactNode;
  tone?: "ok" | "bad" | "warn" | "info" | "mute";
  sub?: string;
}) {
  const tone = props.tone || "info";
  return (
    <div className={"stat stat-" + tone}>
      <div className="stat-value">{props.value}</div>
      <div className="stat-label">{props.label}</div>
      {props.sub ? <div className="stat-sub">{props.sub}</div> : null}
    </div>
  );
}

export function Degraded(props: { reasons: string[] }) {
  if (!props.reasons || props.reasons.length === 0) return null;
  return (
    <div className="degraded">
      <strong>降级 DEGRADED</strong>
      <ul>
        {props.reasons.map((r, i) => (
          <li key={i}>{r}</li>
        ))}
      </ul>
    </div>
  );
}

export function ErrorBox(props: { error: Error | string | null }) {
  if (!props.error) return null;
  const text = typeof props.error === "string" ? props.error : props.error.message;
  return (
    <div className="errorbox" data-testid="errorbox">
      {"错误 ERROR — " + text}
    </div>
  );
}

// Render-crash fallback (guide §A row 32: 错误边界): when a route throws
// during render, the shell survives and shows this notice instead of a
// white screen. Errors are also forwarded to the console for forensics.
export class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): { error: Error } {
    return { error };
  }

  componentDidCatch(error: Error): void {
    console.error("SpecProof render boundary caught:", error);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="errorbox" data-testid="error-boundary" role="alert">
          {"错误 ERROR — 页面渲染异常, 已降级 (error boundary): " +
            (this.state.error.message || String(this.state.error))}
          <div style={{ marginTop: 8 }}>
            <a className="btn btn-ghost btn-sm" href="#/dashboard">
              ← 返回总览
            </a>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export function Empty(props: { text: string }) {
  return <div className="empty">{props.text}</div>;
}

export function Spinner() {
  return <div className="spinner">加载中 LOADING…</div>;
}

export function fmtPct(x: number | null | undefined): string {
  if (x === null || x === undefined) return "—";
  return (x * 100).toFixed(1) + "%";
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export function shortId(id: string | undefined): string {
  return (id || "").slice(0, 8);
}

export function verdictTone(v: string | undefined): "ok" | "bad" | "warn" | "mute" {
  if (v === "VERIFIED") return "ok";
  if (v === "BLOCKED" || v === "FAILED" || v === "ERROR") return "bad";
  if (v === "NEEDS REVIEW") return "warn";
  return "mute";
}

export function severityTone(s: string | undefined): "bad" | "warn" | "info" {
  if (s === "BLOCKER") return "bad";
  if (s === "MAJOR") return "warn";
  return "info";
}

export function kv(label: string, value: ReactNode): ReactNode {
  return (
    <div className="kv">
      <span className="kv-label">{label}</span>
      <span className="kv-value">{value}</span>
    </div>
  );
}
