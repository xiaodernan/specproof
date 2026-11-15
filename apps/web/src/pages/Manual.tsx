import { useCallback, useState } from "react";
import { useI18n } from "../i18n";
import { MANUAL } from "./manual.copy";
import LocalEcho from "./LocalEcho";
import "../styles/manual.css";

/**
 * The SpecProof Manual — the pocket card frozen into the app itself, so a
 * new operator can open Route > Evidence > Manual (or sign in and tap it)
 * and read the 30-second tutorial without leaving the browser.
 *
 * Print-ready: the page is designed to shed its chrome on A4 (see print.css),
 * so "I need a physical page right now" is one keystroke away.
 */
export default function Manual() {
  const { locale } = useI18n();
  const [copied, setCopied] = useState<string | null>(null);

  const copy = useCallback(async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(id);
      window.setTimeout(() => setCopied(null), 1400);
    } catch {
      window.prompt("", text);
    }
  }, []);

  return (
    <div className="manual-page">
      <div className="page-head">
        <h1>{locale === "zh" ? "说明书" : "Manual"} <span className="manual-en">SPECROOF POCKET CARD</span></h1>
        <div className="page-sub">{MANUAL.lead[locale]}</div>
      </div>

      <LocalEcho />
      <div className="manual-paper print-area">
        <p className="manual-kicker">{MANUAL.subtitle[locale]}</p>

        {MANUAL.sections.map((section, idx) => (
          <section key={idx} className="manual-section">
            <h2>{section.title[locale]}</h2>
            <ol className="manual-list">
              {section.rows[locale].map((row, i) => <li key={i}>{row}</li>)}
            </ol>
          </section>
        ))}

        <section className="manual-section">
          <h2>{locale === "zh" ? "五条命令（与仓库一致）" : "Five commands (mirror the repo)"}</h2>
          <ul className="manual-cmd-list">
            {MANUAL.commands.map((cmd) => (
              <li key={cmd.id} className="manual-cmd">
                <div className="manual-cmd-head">
                  <strong>{cmd.title[locale]}</strong>
                  <button
                    type="button"
                    className="manual-copy"
                    aria-pressed={copied === cmd.id}
                    onClick={() => copy(cmd.id, cmd.body)}
                  >
                    {copied === cmd.id ? MANUAL.copiedLabel[locale] : MANUAL.copyLabel[locale]}
                  </button>
                </div>
                <code>{cmd.body}</code>
              </li>
            ))}
          </ul>
        </section>

        <p className="manual-punchline">{MANUAL.punchline[locale]}</p>
      </div>
    </div>
  );
}
