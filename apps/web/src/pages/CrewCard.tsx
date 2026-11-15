import { useCallback } from "react";
import { useI18n } from "../i18n";
import stats from "./repoStats.json";
import evidence from "./evidence.json";
import unsigned from "./unsigned.json";
import { ProductIcon } from "../ui/ProductIcon";
import "../styles/crew.css";

/**
 * The Crew Card — a print-only A4 "field card" of this repository at this
 * commit. It is invisible on screen; one button (in the Last Call page)
 * arms print media and this card appears: repo, measurements, evidence
 * verdict, the three unsigned states — all git-tracked facts, nothing
 * else, printed with the reader's real clock and no signatures.
 */
export default function CrewCard(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string): string => (zh ? a : b);

  const print = useCallback(() => {
    window.print();
  }, []);

  const generated = new Date().toISOString().slice(0, 10);
  const latest = evidence.latest ?? null;
  const audit = unsigned.checks ?? [];
  const obs = audit.find((c) => c.id === "observability-signature")?.status ?? "awaiting-signature";
  const wk = audit.find((c) => c.id === "weekly-stress-merged")?.status ?? "missing";
  const port = audit.find((c) => c.id === "port-8000-answers")?.status ?? "port-free";

  return (
    <>
      <button type="button" className="crew-print-button" onClick={print}>
        <ProductIcon name="scroll" size={13} /> {L("打印船员卡", "Print the field card")}
      </button>

      {/* print-only card: display:none on screen; shown only for print media */}
      <section className="crew-card" aria-label={L("船员字段卡", "The SpecProof field card")}>
        <header className="crew-card-head">
          <p className="crew-card-org">xiaodernan/specproof</p>
          <h2 className="crew-card-title">{L("SpecProof · 船员卡", "SpecProof · FIELD CARD")}</h2>
          <p className="crew-card-date">{L("打印于", "printed at")} {generated}</p>
        </header>
        <div className="crew-card-grid">
          <div><strong>{String(stats.git_commit_count)}</strong><span>{L("提交 commits", "commits")}</span></div>
          <div><strong>{(stats.ledger_sections).toLocaleString()}</strong><span>{L("账本节数", "ledger sections")}</span></div>
          <div><strong>{(stats.worldbook_sections).toLocaleString()}</strong><span>{L("世界书卷数 (zh/en)", "world-book volumes (zh/en)")}</span></div>
          <div><strong>{(stats.total_lines_of_source).toLocaleString()}</strong><span>{L("源码行数", "source lines")}</span></div>
          <div><strong>{(stats.python_test_files).toLocaleString()}</strong><span>{L("Python 测试文件", "Python test files")}</span></div>
          <div><strong>{(stats.web_test_files).toLocaleString()}</strong><span>{L("前端测试文件", "web test files")}</span></div>
          <div><strong>{latest ? `${Math.round(latest.worst_p99_ms)}ms` : "—"}</strong><span>{L("证据 · worst p99", "evidence · worst p99")}<sup>1</sup></span></div>
          <div><strong>{latest ? latest.verdict : "—"}</strong><span>{L("证据 · 判定", "evidence · verdict")}<sup>1</sup></span></div>
        </div>
        <div className="crew-card-audit">
          <p className="crew-card-lane">{L("欠签（审计于本机；从缺不补）", "unsigned (audited on this host; no filling in)")}</p>
          <ul>
            <li>{L("真·fleet 遥测 · OBSERVABILITY.md 签字：", "real fleet telemetry · OBSERVABILITY.md sign-off: ")}<strong>{obs}</strong></li>
            <li>{L("每周一敲门 · weekly-stress.yml 合入：", "the Monday knock · weekly-stress.yml merged: ")}<strong>{wk}</strong></li>
            <li>{L("端口 8000 · 此刻谁在答：", "port 8000 · who answers right now: ")}<strong>{port}</strong></li>
          </ul>
        </div>
        <footer className="crew-card-foot">
          <p>
            {zh
              ? "本船员卡只刻本仓库 git-tracked 的事实。它不是签名证书、不是验收章、不是对任何人的承诺——每一个数字都能敲开："
              : "This card prints only git-tracked facts. It is not a signature, not a seal, not a promise to anyone — every digit can be re-examined:"}
          </p>
          <code>git log --oneline -1 && python scripts/build_repo_stats.py && python scripts/audit_unsigned.py</code>
          <p className="crew-card-honesty">
            {zh
              ? "出厂源：chronicle.json · repoStats.json · evidence.json · unsigned.json（全部 git-tracked，全部可 git show）。#1858"
              : "sources: chronicle.json · repoStats.json · evidence.json · unsigned.json (all git-tracked, all git-showable). #1858"}
          </p>
        </footer>
      </section>
    </>
  );
}
