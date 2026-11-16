import { useI18n } from "../i18n";
import stats from "./repoStats.json";
import "../styles/stats.css";

/**
 * Iron Census — the repo, measured, not narrated.
 * Every figure below is derived from `git ls-files` + on-disk bytes. Nothing
 * here is estimated, invented or rounded by a human hand; the numbers were
 * produced by `scripts/build_repo_stats.py` and are trivially re-runnable.
 */

const LANG_ORDER = Object.entries(stats.by_language as Record<string, { files: number; lines: number; bytes: number }>)
  .sort((a, b) => b[1].lines - a[1].lines);

const LANG_BAR_COLOR: Record<string, string> = {
  Python: "var(--pigment-steel-59)", TypeScript: "var(--archive-amber-lantern-accent)", "TypeScript/TSX": "var(--pigment-gilt-44)",
  "JavaScript": "var(--pigment-gilt-45)", "JavaScript/ESM": "var(--pigment-gilt-46)", Java: "var(--pigment-oxide-15)",
  Markdown: "var(--pigment-jade-36)", CSS: "var(--pigment-steel-60)", YAML: "var(--accent-2-500)", JSON: "var(--pigment-oxide-16)",
  SQL: "var(--pigment-oxide-12)", HTML: "var(--accent-2-400)",
};

export default function Stats() {
  const { t, locale } = useI18n();
  const langMax = LANG_ORDER[0]?.[1].lines ?? 1;
  const bytesMB = (stats.total_bytes / 1024 / 1024).toFixed(1);
  const filName = locale === "zh" ? "个文件" : "files";
  const locName = locale === "zh" ? "行源码" : "source lines";
  const mbName = locale === "zh" ? "MB" : "MB";
  const commitName = locale === "zh" ? "次提交" : "commits";
  const testName = locale === "zh" ? "个测试文件" : "test files";

  return (
    <div className="census-page">
      <div className="page-head">
        <h1>{t("census.title")} <span className="census-en">{t("census.subtitle")}</span></h1>
        <div className="page-sub">{t("census.lead")}</div>
      </div>

      <div className="census-hero">
        <div className="census-tile">
          <p className="census-value">{stats.repository_files.toLocaleString()}</p>
          <p className="census-label">{filName}</p>
        </div>
        <div className="census-tile">
          <p className="census-value">{stats.total_lines_of_source.toLocaleString()}</p>
          <p className="census-label">{locName}</p>
        </div>
        <div className="census-tile">
          <p className="census-value">{bytesMB}</p>
          <p className="census-label">{mbName}</p>
        </div>
        <div className="census-tile">
          <p className="census-value">{stats.git_commit_count.toLocaleString()}</p>
          <p className="census-label">{commitName}</p>
        </div>
        <div className="census-tile">
          <p className="census-value">{stats.python_test_files + stats.web_test_files}</p>
          <p className="census-label">{testName}</p>
        </div>
        <div className="census-tile">
          <p className="census-value">{Math.round(stats.ledger_bytes_kB).toLocaleString()}<span className="census-unit">KB</span></p>
          <p className="census-label">{t("census.ledger")}</p>
        </div>
        <div className="census-tile">
          <p className="census-value">{(stats.world_bytes_zh / 1024).toFixed(1)}<span className="census-unit">KB</span></p>
          <p className="census-label">{t("census.worldChinese")}</p>
        </div>
        <div className="census-tile">
          <p className="census-value">{(stats.world_bytes_en / 1024).toFixed(1)}<span className="census-unit">KB</span></p>
          <p className="census-label">{t("census.worldEnglish")}</p>
        </div>
      </div>

      <section className="census-lang">
        <h2>{t("census.langTitle")}</h2>
        <ol className="census-lang-list">
          {LANG_ORDER.slice(0, 14).map(([lang, stat]) => (
            <li key={lang} className="census-lang-row">
              <span className="census-lang-name">{lang}</span>
              <div className="census-lang-bar">
                <div
                  style={{ width: `${Math.round((stat.lines / langMax) * 100)}%`, background: LANG_BAR_COLOR[lang] ?? "var(--pigment-steel-61)" }}
                />
              </div>
              <span className="census-lang-num">
                <strong>{stat.lines.toLocaleString()}</strong> {t("census.lines")} · {stat.files.toLocaleString()} {filName}
              </span>
            </li>
          ))}
        </ol>

        <p className="census-foot">{t("census.foot")}</p>
      </section>
    </div>
  );
}
