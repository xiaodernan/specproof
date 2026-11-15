import { useEffect, useState } from "react";
import "../styles/verification.css";
import { useNavigate } from "../hooks/navigate";
import {
  loadTourProgress,
  isTourSealed,
  resetTourProgress,
  saveTourProgress,
  toggleStation,
  tourCompletionCount,
  type TourStation,
  type TourProgress,
} from "../ui/tour";
import { loadOnboardingProgress, routeKeyForVisit } from "../ui/onboarding";
import { TOUR_BY_LOCALE } from "./tour.copy";
import { useI18n } from "../i18n";
import { Button } from "../ui";

function Station({
  station,
  done,
  visited,
  onToggle,
}: {
  station: TourStation;
  done: boolean;
  visited: boolean;
  onToggle: () => void;
}) {
  const { t, locale } = useI18n();
  const navigate = useNavigate();
  return (
    <article className={"tour-station" + (done ? " tour-station-done" : "")}>
      <div className="tour-seal" aria-hidden={!done}>{done ? (locale === "zh" ? "是" : "SEAL") : ""}</div>
      <div className="tour-body">
        <div className="tour-chapter">{station.chapter}</div>
        <h2>{station.title}</h2>
        <div className="tour-en">{station.en}</div>
        <p className="tour-narrate">{station.narrate}</p>
        <p className="tour-task">
          <strong>{t("tour.task")}</strong>{" "}
          {station.task}
        </p>
        <p className="tour-tip">
          <span className="tour-tip-label">{t("tour.tip")}</span>
          {station.tip}
        </p>
        <div className="tour-actions">
          <Button size="sm" variant="ghost" onClick={() => navigate(station.route)}>
            {station.routeLabel} →
          </Button>
          <Button
            size="sm"
            variant={done ? "ghost" : "primary"}
            onClick={onToggle}
            aria-pressed={done}
            disabled={!visited && !done}
            title={visited || done ? undefined : (locale === "zh" ? "先到访此页，才能盖章。" : "Visit this page first to seal this station.")}
          >
            {done ? t("tour.unseal") : t("tour.seal")}
          </Button>
        </div>
        {!visited && !done && (
          <p className="tour-visit-hint" role="status">
            {locale === "zh"
              ? "本机还没去过这里——先打开下面的链接至少一次，本按钮才会亮。"
              : "This browser hasn't been there yet — open the link below at least once and this button will light up."}
          </p>
        )}
      </div>
    </article>
  );
}

export default function Tour() {
  const { t, locale } = useI18n();
  const stations = TOUR_BY_LOCALE[locale];
  const [{ progress, corrupted }, setState] = useState(() => loadTourProgress());
  const [saveFailed, setSaveFailed] = useState(false);
  const [visits, setVisits] = useState<Record<string, string>>(() => {
    const r = loadOnboardingProgress();
    return r.status === "ok" ? r.progress.visited : {};
  });

  // Refresh visits cache on each hashchange (the page is static between events, but let's be honest: we read localStorage fresh)
  useEffect(() => {
    const handler = () => {
      const r = loadOnboardingProgress();
      if (r.status === "ok") setVisits(r.progress.visited);
    };
    window.addEventListener("hashchange", handler);
    handler();
    return () => window.removeEventListener("hashchange", handler);
  }, []);

  const visited = (station: TourStation) => {
    const key = routeKeyForVisit(station.route);
    return key ? Boolean(visits[key]) : true;
  };

  const refresh = (next: TourProgress) => {
    const saved = saveTourProgress(next);
    setSaveFailed(!saved);
    setState({ progress: next, corrupted: false });
    setVisits(() => {
      const r = loadOnboardingProgress();
      return r.status === "ok" ? r.progress.visited : {};
    });
  };

  const toggle = (id: TourStation["id"]) => {
    // Seal is only meaningful if the visit was recorded — that is the contract.
    const station = stations.find((s) => s.id === id);
    if (station && !visited(station)) return;
    refresh(toggleStation(progress, id));
  };

  const reset = () => {
    setSaveFailed(false);
    setState({ progress: resetTourProgress(), corrupted: false });
  };

  const completed = tourCompletionCount(progress);
  const sealed = isTourSealed(progress);
  const verifiedVisits = stations.filter((s) => visited(s)).length;
  const specimenSummary = `${completed} / ${stations.length} ${t("tour.progress")}`;

  return (
    <div className="tour-page">
      <div className="page-head">
        <h1>{t("tour.title")} <span className="tour-en">{t("tour.subtitle")}</span></h1>
        <div className="page-sub" title="SIX SCROLLS OF ORIENTATION">
          {t("tour.lead")}
        </div>
      </div>

      <div className="tour-prologue">
        <span className="tour-prologue-mark" aria-hidden="true">○</span>
        <p>{locale === "zh" ? "巡览不是清单，是第一夜之旅。所谓「走完巡览」——不是每一页都点过，而是每一桩真实的查验证你都被自己按了一次手印。六卷盖了五枚，你比进来的你更像验收官；盖了第六枚，章上的字便从「访客」变成「验收官」。" : "The tour is not a checklist; it is the first night's walk. “Completed” does not mean you clicked every page — it means each six expeditions was witnessed by your own hand. Five seals and you are no longer a guest; six seals say you are one of us."}</p>
      </div>

      {corrupted ? (
        <div className="degraded" role="status">
          <strong>{t("tour.corrupted")}</strong>
          <p>localStorage 里的 specproof_tour_v1 解析失败——可能是手动改坏了，或者浏览器换了 profile。这不等于没走过：本页按全新状态呈现，旧印记已被隔离。</p>
        </div>
      ) : null}

      {saveFailed ? (
        <div className="degraded" role="status">
          <strong>{t("tour.saveFailed")}</strong>
          <p>本机存储被禁用（可能是无痕模式或策略）。此处的「完成」不会在刷新后保留——界面如实告诉你这一点，而不是骗你「已保存」。</p>
        </div>
      ) : null}

      <div className="tour-progress" aria-label={t("tour.title")}>
        <div className="tour-progress-row">
          <span className="tour-progress-label">{specimenSummary}</span>
          <span className="tour-progress-verified muted">· {locale === "zh" ? `已验证 ${verifiedVisits} / ${stations.length} 站` : `verified ${verifiedVisits} / ${stations.length}`}</span>
          <div className="tour-progress-rail" role="progressbar" aria-valuenow={completed} aria-valuemin={0} aria-valuemax={stations.length} aria-label={t("tour.progress")}>
            <div className="tour-progress-fill" style={{ width: `${(completed / stations.length) * 100}%` }} />
          </div>
        </div>
        {sealed ? (
          <div className="tour-sealed" role="status">
            <span className="tour-sealed-stamp" aria-hidden="true">{locale === "zh" ? "验讫" : "SEALED"}</span>
            <div>
              <strong>{t("tour.sealedTitle")}</strong>
              <p>{t("tour.sealedBody")}</p>
            </div>
          </div>
        ) : null}
      </div>

      <div className="tour-stations">
        {stations.map((station) => (
          <Station
            key={station.id}
            station={station}
            done={progress.completed.includes(station.id)}
            visited={visited(station)}
            onToggle={() => toggle(station.id)}
          />
        ))}
      </div>

      <div className="tour-footer">
        <Button variant="ghost" size="sm" onClick={reset}>{t("tour.reset")}</Button>
        <span className="tour-footnote">{locale === "zh" ? "盖章证明你按过手印；按手印证明你读过条款；不读条款按钮就不可触。" : "An empty hand does not seal this roll — open the page first, then come back to press the seal."}</span>
      </div>
    </div>
  );
}
