import "../styles/verification.css";
import { CLOSING_BY_LOCALE, SCROLLS_BY_LOCALE } from "./epic.copy";
import { useI18n } from "../i18n";

// 史诗 · The Chronicles of SpecProof —— 给一切验收动作一个起源与一个收束。
// 本页所有数字、提交号、账本条目标号全部是本项目真实发生过的事，
// 每一章底部的「史官细则」都能在 docs/operations/DEEP_OPTIMIZATION_PLAN.md 与 git log 中找到对应条目。
// 凡本项目尚未完成的事，一律写为"未完"而不是"已成"。

export default function Epic() {
  const { t, locale } = useI18n();
  const scrolls = SCROLLS_BY_LOCALE[locale];
  const closing = CLOSING_BY_LOCALE[locale];
  return (
    <div className="chronicles-page">
      <div className="page-head">
        <h1>{t("epic.title")} <span className="chronicles-en">{t("epic.subtitle")}</span></h1>
        <div className="page-sub" title="THE LEDGER AND THE LEGEND">
          {t("epic.lead")}
        </div>
      </div>

      <div className="chronicles-prologue">
        <span className="chronicles-prologue-mark" aria-hidden="true">{locale === "zh" ? "序" : "P"}</span>
        <p>
          此书始于一个简单的问题：<strong>AI 写的代码，谁配说「过了」？</strong>答案不是模型的自信、也不是评审的好运气，而是<strong>一炉可复现的铁证</strong>：契约编译成法律、差分执行成证言、矩阵列出罪名，再由确定性策略定谳。SpecProof 不是一个「检查代码的工具」，它是一台为每个变更验明来路的<strong>验收机器</strong>。
        </p>
      </div>

      {scrolls.map((scroll) => (
        <article className="chronicles-scroll" key={scroll.num} id={"scroll-" + scroll.num.replace(/[^0-9a-zA-Z]/g, "")}>
          <div className="chronicles-spine" aria-hidden="true"><span>{scroll.num.slice(1)}</span></div>
          <div className="chronicles-body">
            <header className="chronicles-scroll-head">
              <span className="chronicles-seal">{scroll.num.slice(1)}</span>
              <div>
                <h2>{scroll.title}</h2>
                <div className="chronicles-en">{scroll.en} · {scroll.era}</div>
              </div>
            </header>
            {scroll.verses.map((v, i) => (
              <p className="chronicles-verse" key={i}>{v}</p>
            ))}
            <div className="chronicles-details">
              <div className="chronicles-details-title">{t("epic.chronicleNote")}</div>
              <dl>
                {scroll.details.map((d) => (
                  <div className="chronicles-detail-row" key={d.label}>
                    <dt>{d.label}</dt>
                    <dd>{d.value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </div>
        </article>
      ))}

      <div className="chronicles-closing">
        <span className="chronicles-prologue-mark" aria-hidden="true">尾</span>
        <div>
          <h3>{closing[0]}</h3>
          <p>{closing[1]}</p>
          <p>{closing[2]}</p>
        </div>
      </div>

      <p className="chronicles-colophon muted">
        {t("epic.colophon")}
      </p>
    </div>
  );
}
