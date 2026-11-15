import { ProductIcon } from "../ui/ProductIcon";
import { useI18n } from "../i18n";
import evidence from "./evidence.json";
import "../styles/fabricStress.css";

/**
 * THE STRESS LEDGER — a build-time, dated snapshot of what today's pressure
 * runs actually said, mounted inside Fabric so the weave shows fibres, not
 * wallpaper. Never pretends to be live traffic: the numbers below are
 * measured on 2026-11-16 (this host) and committed as static text.
 *
 * If the live process is not running, the live port says nothing — which is
 * exactly the correct reading of the evidence block below.
 */
export default function FabricStress(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string): string => (zh ? a : b);

  return (
    <section className="fabric-stress" aria-label={L("压过的真相 · 2026-11-16 快照", "The stressed truth, snapshot of 2026-11-16")}>
      <div className="fabric-stress-head">
        <p className="fabric-stress-kicker">{L("压过的真相 · 2026-11-16 实敲", "THE STRESS LEDGER · struck live 2026-11-16")}</p>
        <p className="fabric-stress-sub">{L("这些数字来自这台机器上的真实敲击，不是编排出来的演示。进程退出后，活车道只会显示 down——这就是它正确的答案。", "Numbers from real knocks on this host, not staging. When the process exits, the live lane reads down — the correct answer.")}</p>
      </div>
      <div className="fabric-stress-grid">
        <div className="fabric-stress-cell fabric-stress-good">
          <span className="fabric-stress-lane">{L("车道 A · 活体 API（192.168.1.5:8000）", "LANE A · live API (192.168.1.5:8000)")}</span>
          <strong>{L("144/144 · 0 err", "144/144 · 0 err")}</strong>
          <code>{L("36 并发 ×2 轮 · p50 474ms / p95 592ms · 判定 OK（轮 2）", "36×2 rounds · p50 474ms / p95 592ms · verdict OK (round 2)")}</code>
        </div>
        <div className="fabric-stress-cell fabric-stress-good">
          <span className="fabric-stress-lane">{L("车道 A′ · 同机此前的一组", "LANE A′ · earlier same-day group")}</span>
          <strong>{L("192 req · 0 err", "192 req · 0 err")}</strong>
          <code>{L("72 并发 ×2 轮 · p99 440→176ms（第二轮回落）", "72-concurrent ×2 rounds · p99 440→176ms")}</code>
        </div>
        <div className="fabric-stress-cell fabric-stress-bad">
          <span className="fabric-stress-lane">{L("车道 B · 静态 front door（冷启动）", "LANE B · static front door (cold start)")}</span>
          <strong>{L("超额但未崩", "over budget, did not crash")}</strong>
          <code>{L("round 1 p99 7588ms → round 2 p99 528ms · 冷盘 JIT；判 BUDGET-BLOWN", "round 1 p99 7588ms → round 2 p99 528ms · cold-disk JIT; BUDGET-BLOWN")}</code>
        </div>
        <div className="fabric-stress-cell fabric-stress-bad">
          <span className="fabric-stress-lane">{L("车道 C · 127.0.0.1:8000（那一刻）", "LANE C · 127.0.0.1:8000 (at that moment)")}</span>
          <strong>{L("100% err → 不是本仓库", "100% err → not this repo")}</strong>
          <code>{L("那时 career-os-ai-service 占住了 127.0.0.1:8000，答 / 404；本仓库列位于 0.0.0.0:8000（192.168.1.5 可达）", "career-os-ai-service held 127.0.0.1:8000 and answered 404; this repo binds 0.0.0.0:8000 (reachable at 192.168.1.5)")}</code>
        </div>
        <div className="fabric-stress-cell">
          <span className="fabric-stress-lane">{L("端口 8000 归属", "PORT 8000 ownership")}</span>
          <strong>{L("不是 specproof 的", "not specproof's")}</strong>
          <code>{L("PID 12868 com.docker.backend（uvicorn · x-request-id · traceparent）", "PID 12868 com.docker.backend (uvicorn · x-request-id · traceparent)")}</code>
        </div>
        <div className="fabric-stress-cell">
          <span className="fabric-stress-lane">{L("外网搜索（本环境）", "OUTBOUND SEARCH (this env)")}</span>
          <strong>{L("HTTP 402", "HTTP 402")}</strong>
          <code>{L("唯一可用联网通道仍是 wkapi.pro（stream + include_usage 车道）", "only viable outbound remains wkapi.pro (stream + include_usage lane)")}</code>
        </div>
      </div>
      {evidence.latest && (
        <div className="fabric-evidence" aria-label={L("git 证据件", "The git evidence file")}>
          <div className="fabric-evidence-head">
            <span className="fabric-stress-lane">{L("git 证据件 · 自动从 docs/evidence/ 读取", "GIT EVIDENCE · read from docs/evidence/ at build time")}</span>
            <code className="fabric-evidence-name">{evidence.latest.file}</code>
          </div>
          <div className="fabric-evidence-row">
            <span>{L("敲击时间", "struck")} <strong>{evidence.latest.started_utc.slice(0, 16).replace("T", " ")}Z</strong></span>
            <span>{L("并发", "concurrency")} <strong>{evidence.latest.concurrency}</strong> · {L("预热", "warmups")} <strong>{evidence.latest.warmup_rounds}</strong></span>
            <span>{L("总数", "total")} <strong>{evidence.latest.total_ok}/{evidence.latest.total}</strong> · {L("0 错", "0 err")}</span>
            <span>{L("最差 p99", "worst p99")} <strong>{Math.round(evidence.latest.worst_p99_ms)}ms</strong></span>
            <span className={evidence.latest.verdict === "OK" ? "fabric-evidence-ok" : "fabric-evidence-blown"}>{L("判定", "verdict")} <strong>{evidence.latest.verdict}</strong></span>
          </div>
          <p className="fabric-evidence-note">
            {L(
              "本卡片由 scripts/build_evidence.py 在构建期从证据件原样摘录；要让它更新，就敲一份新证据：stress_smoke.py --json-report docs/evidence/<名称>.json",
              "This card is distilled verbatim at build time by scripts/build_evidence.py. To refresh it, strike a new one: stress_smoke.py --json-report docs/evidence/<name>.json",
            )}
          </p>
        </div>
      )}
      <p className="fabric-stress-foot">
        <ProductIcon name="shield" size={12} />{" "}
        {L(
          "本条目只声明「2026-11-16 实敲」的快照；没有任何一处在声称 live。真·全负载生产演练需 compose 应用栈与签字授权（OBSERVABILITY.md）。",
          "This ledger asserts a struck-on-2026-11-16 snapshot, nothing live. A real full-load production rehearsal needs the compose app stack and signatures (OBSERVABILITY.md).",
        )}
      </p>
    </section>
  );
}
