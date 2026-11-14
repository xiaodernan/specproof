import { useState } from "react";
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
import { TOUR_BY_LOCALE } from "./tour.copy";
import { useI18n } from "../i18n";
import { Button } from "../ui";

function Station({
  station,
  done,
  onToggle,
}: {
  station: TourStation;
  done: boolean;
  onToggle: () => void;
}) {
  const { t, locale } = useI18n();
  const navigate = useNavigate();
  return (
    <article className={"tour-station" + (done ? " tour-station-done" : "")}>
      <div className="tour-seal" aria-hidden={!done}>{done ? (locale === "zh" ? "验" : "SEAL") : ""}</div>
      <div className="tour-body">
        <div className="tour-chapter">{station.chapter}</div>
        <h2>{station.title}</h2>
        <div className="tour-en">{station.en}</div>
        <p className="tour-narrate">{station.narrate}</p>
        <p className="tour-task">
          <strong>{t("tour.task")}：</strong>{" "}
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
          >
            {done ? t("tour.unseal") : t("tour.seal")}
          </Button>
        </div>
      </div>
    </article>
  );
}

export default function Tour() {
  const { t, locale } = useI18n();
  const stations = TOUR_BY_LOCALE[locale];
  const [{ progress, corrupted }, setState] = useState(() => loadTourProgress());
  const [saveFailed, setSaveFailed] = useState(false);

  const refresh = (next: TourProgress) => {
    const saved = saveTourProgress(next);
    setSaveFailed(!saved);
    setState({ progress: next, corrupted: false });
  };

  const toggle = (id: TourStation["id"]) => {
    refresh(toggleStation(progress, id));
  };

  const reset = () => {
    setSaveFailed(false);
    setState({ progress: resetTourProgress(), corrupted: false });
  };

  const completed = tourCompletionCount(progress);
  const sealed = isTourSealed(progress);
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
        <span className="tour-prologue-mark" aria-hidden="true">序</span>
        <p>巡览不是清单，是第一夜之旅。所谓「走完巡览」——不是每一页都点过，而是每一桩真实的查验证你都被自己按了一次手印。六卷盖了五枚，你比进来的你更像验收官；盖了第六枚，章上的字便从「访客」变成「验收官」。</p>
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
          <div className="tour-progress-rail" role="progressbar" aria-valuenow={completed} aria-valuemin={0} aria-valuemax={stations.length} aria-label={t("tour.progress")}>
            <div className="tour-progress-fill" style={{ width: `${(completed / stations.length) * 100}%` }} />
          </div>
        </div>
        {sealed ? (
          <div className="tour-sealed" role="status">
            <span className="tour-sealed-stamp" aria-hidden="true">{locale === "zh" ? "验讫" : "SEALED"}</span>
            <div>
              <strong>{t("tour.sealedTitle")}</strong>
              <span>SpecProof 的史官记下了这一页——你不是本产品的访客了，而是知道这件事、做这件事、敢盖章的人。</span>
            </div>
          </div>
        ) : (
          <p className="tour-hint muted">空着的印记才有意义——每一页你盖上去，都是给自己的。</p>
        )}
      </div>

      {stations.map((st) => (
        <Station key={st.id} station={st} done={progress.completed.includes(st.id)} onToggle={() => toggle(st.id)} />
      ))}

      <div className="tour-reset-row">
        <Button size="sm" variant="ghost" onClick={reset}>
          {t("tour.reset")}
        </Button>
      </div>

      <p className="tour-colophon muted">
        {t("tour.colophon")}
      </p>
    </div>
  );
}
