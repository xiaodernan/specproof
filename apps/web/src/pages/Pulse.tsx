import { useEffect, useRef, useState } from "react";
import { apiGet, type HealthData } from "../api";
import { useI18n } from "../i18n";
import { ProductIcon } from "../ui/ProductIcon";
import "../styles/pulse.css";

/**
 * The Pulse — a browser's own pulse measurement of THIS deployment.
 *
 * Every number here is taken right now by this browser against the backend it
 * can reach: the readiness probe at /api/v1/health, timed locally. It is NOT
 * a fleet SLA, not a TLS east-west probe, not a production acceptance. It is
 * one visitor's clock against the same machine — a thermometer, never a
 * certification.
 *
 * Storage: specproof_pulse_v1 in localStorage (this browser only, read/write
 * honestly, cleared via button).
 */

interface ProbeShape extends HealthData {
  db?: boolean;
  llm_provider?: string;
  llm_ready?: boolean;
  embedding_provider?: string;
  embedding_ready?: boolean;
  build_sha?: string;
}

interface PulseBeart {
  at: string;
  ms: number;
  ok: boolean;
}

const PULSE_KEY = "specproof_pulse_v1";

function readLocalPulses(): PulseBeart[] {
  try {
    const raw = window.localStorage.getItem(PULSE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as PulseBeart[];
    return Array.isArray(parsed) ? parsed.filter((p) => typeof p.ms === "number").slice(-50) : [];
  } catch {
    return [];
  }
}

function writeLocalPulses(rows: PulseBeart[]): boolean {
  try {
    window.localStorage.setItem(PULSE_KEY, JSON.stringify(rows.slice(-50)));
    return true;
  } catch {
    return false;
  }
}

export default function Pulse(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string): string => (zh ? a : b);

  const [probe, setProbe] = useState<ProbeShape | null>(null);
  const [probeMs, setProbeMs] = useState<number | null>(null);
  const [probeError, setProbeError] = useState<string | null>(null);
  const [history, setHistory] = useState<PulseBeart[]>(() => readLocalPulses());
  const [blast, setBlast] = useState<Array<{ ms: number; ok: boolean; error?: string }> | null>(null);
  const [blasting, setBlasting] = useState(false);
  const blastTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  async function measureOnce(): Promise<PulseBeart> {
    const started = performance.now();
    try {
      const data = (await apiGet<ProbeShape>("/api/v1/health")) as ProbeShape;
      const ms = Math.round(performance.now() - started);
      setProbe(data);
      setProbeMs(ms);
      setProbeError(null);
      return { at: new Date().toISOString(), ms, ok: true };
    } catch (e: unknown) {
      const ms = Math.round(performance.now() - started);
      setProbe(null);
      setProbeMs(ms);
      setProbeError(e instanceof Error ? e.message : String(e));
      return { at: new Date().toISOString(), ms, ok: false };
    }
  }

  useEffect(() => {
    let alive = true;
    measureOnce().then((row) => {
      if (!alive) return;
      setHistory((prev) => {
        const next = [...prev, row].slice(-50);
        writeLocalPulses(next);
        return next;
      });
    }).catch(() => { /* measureOnce never rejects */ });
    return () => { alive = false; };
  }, []);

  async function fireBlast() {
    if (blasting) return;
    setBlasting(true);
    setBlast([]);
    const out: Array<{ ms: number; ok: boolean; error?: string }> = [];
    for (let i = 0; i < 5; i += 1) {
      const started = performance.now();
      try {
        await apiGet<ProbeShape>("/api/v1/health");
        out.push({ ms: Math.round(performance.now() - started), ok: true });
      } catch (e: unknown) {
        out.push({ ms: Math.round(performance.now() - started), ok: false, error: e instanceof Error ? e.message : String(e) });
      }
      setBlast([...out]);
      await new Promise((r) => { blastTimer.current = setTimeout(r, 400) as unknown as ReturnType<typeof setInterval>; });
    }
    setBlasting(false);
  }

  useEffect(() => () => { if (blastTimer.current) clearTimeout(blastTimer.current); }, []);

  const okCount = blast?.filter((b) => b.ok).length ?? 0;
  const blastMax = blast && blast.length ? Math.max(...blast.map((b) => b.ms)) : 0;
  const blastAvg = blast && blast.length ? Math.round(blast.reduce((a, b) => a + b.ms, 0) / blast.length) : 0;
  const maxHist = Math.max(...history.map((h) => h.ms), 1);

  const rows: Array<{ label: string; value: string; ok?: boolean }> = probe
    ? [
        { label: L("总体", "Overall"), value: probe.status ?? L("未上报", "not reported"), ok: probe.status === "ok" },
        { label: L("数据库", "Database"), value: probe.db === undefined ? L("未上报", "not reported") : probe.db ? "db=ok" : "db=FAIL", ok: probe.db !== false },
        { label: L("LLM 连通", "LLM ready"), value: probe.llm_ready === undefined ? L("未上报", "not reported") : probe.llm_ready ? (probe.llm_provider ?? "llm ok") : "not ready", ok: probe.llm_ready !== false },
        { label: L("嵌入", "Embedding"), value: probe.embedding_ready === undefined ? L("未上报", "not reported") : probe.embedding_ready ? (probe.embedding_provider ?? "ok") : "not ready", ok: probe.embedding_ready !== false },
        { label: L("构建", "Build"), value: probe.build_sha ?? L("未上报", "not reported"), ok: true },
      ]
    : [];

  return (
    <div className="pulse-page">
      <header className="pulse-mast">
        <p className="pulse-kicker">{L("此 刻 的 一 次", "ONE VISITOR, ONE MOMENT")}</p>
        <h1>{L("服务脉搏", "Service Pulse")} <span className="pulse-en">{L("SERVICE PULSE · 此浏览器，不是舰队", "ONE BROWSER, NOT A FLEET")}</span></h1>
        <p className="pulse-lead">
          {L(
            "本页是这个浏览器敲一次 /api/v1/health 听见的回声，不是舰队 SLA。读数真——但只代表这一台机器在这一秒里的样子。要看船队级真正眼睛，走 docs/operations/OBSERVABILITY.md。",
            "This page is one browser's echo against /api/v1/health — not a fleet SLA. The figures are true, but they only describe this one machine at this one second. For the fleet's real eyes, see docs/operations/OBSERVABILITY.md.",
          )}
        </p>
        <div className="pulse-readout">
          <span className="pulse-readout-value">{probeMs === null ? "—" : `${probeMs}ms`}</span>
          <span className="pulse-readout-label">{probeError ? L("未能应答", "no answer") : L("本次读取", "this read")}</span>
          {probeError && <span className="pulse-readout-error" role="alert">{probeError.slice(0, 180)}</span>}
        </div>
      </header>

      <div className="pulse-grid">
        <section className="pulse-panel pulse-report-panel" aria-label={L("当前应答", "current answer")}>
          <h2>{L("应答回声", "The Answer's Echo")}</h2>
          {rows.length === 0 ? (
            <p className="pulse-empty">{L("还没有读到任何东西——", "Nothing here yet —")} {probeError ?? (zh ? "等待完成" : "waiting")}</p>
          ) : (
            <ul className="pulse-kv">
              {rows.map((r) => (
                <li key={r.label} className="pulse-kv-row">
                  <span className="pulse-kv-label">{r.label}</span>
                  <code className={"pulse-kv-value" + (r.ok === false ? " pulse-kv-bad" : "")}>{r.value}</code>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="pulse-panel pulse-blast-panel">
          <h2>{L("五连敲击", "The Five Knockings")}</h2>
          <p className="pulse-blast-note">{L("连续 5 次敲击 /api/v1/health（各 400ms 间隔）。任意一次失败不等于系统死了，任一次 ≤1000ms 只是这个浏览器的体感刻度，不是官方阈值。", "Five knocks on /api/v1/health, 400ms apart. Any failure is not death, any sub-second read is this visitor's thermometer — not a rule.")}</p>
          <button className="pulse-blast" onClick={fireBlast} disabled={blasting}>
            {blasting ? L("敲击中…", "Knocking…") : L("敲五下", "Knock five times")}
          </button>
          {blast && (
            <>
              <ol className="pulse-blast-rows">
                {blast.map((b, i) => (
                  <li key={i} className={"pulse-blast-row" + (b.ok ? "" : " pulse-blast-bad")}>
                    <span className="pulse-blast-seq">#{i + 1}</span>
                    <span className="pulse-blast-ms">{b.ms}ms</span>
                    <span className="pulse-blast-state">{b.ok ? "ok" : L("失败", "failed")}</span>
                  </li>
                ))}
              </ol>
              <p className="pulse-blast-summary">{L("成功", "ok")} <strong>{okCount}/5</strong> · {L("最慢", "slowest")} <strong>{blastMax}ms</strong> · {L("均值", "avg")} <strong>{blastAvg}ms</strong></p>
            </>
          )}
        </section>

        <section className="pulse-panel pulse-history-panel">
          <div className="pulse-history-head">
            <h2>{L("本机脉搏留存", "Pulse kept on this browser")}</h2>
            <button className="pulse-clear" onClick={() => { window.localStorage.removeItem(PULSE_KEY); setHistory([]); }}>
              {L("清空", "clear")}
            </button>
          </div>
          {history.length === 0 ? (
            <p className="pulse-empty">{L("这浏览器里还没有任何一次脉搏记录——", "This browser has no pulse recorded yet —")}{' '}{L("每次进本页都会记一笔。", "each visit writes one.")}</p>
          ) : (
            <>
              <div className="pulse-sparkbars" role="img" aria-label={L("最近 50 次敲击延迟柱状图", "Last 50 knocks, latency")}>
                {history.map((h, i) => (
                  <div
                    key={i}
                    className={"pulse-sparkbar" + (h.ok ? "" : " pulse-sparkbar-bad")}
                    style={{ height: `${Math.max(6, (h.ms / maxHist) * 100)}%` }}
                    title={`${h.at.slice(0, 19).replace("T", " ")} — ${h.ms}ms${h.ok ? "" : " (failed)"}`}
                  />
                ))}
              </div>
              <p className="pulse-sparknote">{L(`最近 ${history.length} 次 · 只在这个浏览器里 · 每柱高度 = 延迟占用最大值`, `Last ${history.length} · this browser only · bar height = latency vs max`)}</p>
            </>
          )}
        </section>
      </div>

      <footer className="pulse-honesty">
        <ProductIcon name="shield" size={13} />
        <p>
          {zh
            ? "本页读数是这个浏览器对它能到达的后端的体感帧——不是舰队 SLA，不是跨可用区终结证书，不是生产验收。要真正的船队遥测：/metrics 的 OTel/Prom 车道（api/server.py GET /metrics）+ docs/operations/OBSERVABILITY.md + 隐私评审签字。真真切切的生产遥测从不来自某一台笔记本的时钟。"
            : "These readings are one browser's feel of the only backend it can reach — not a fleet SLA, not a cross-AZ end-to-end certificate, not a production acceptance. For the real fleet: the /metrics OTel/Prom lane (api/server.py @app.get(\"/metrics\")) + docs/operations/OBSERVABILITY.md + privacy sign-off. Real production telemetry never comes from a laptop's clock."}
        </p>
      </footer>
    </div>
  );
}
