import { useState } from "react";
import "../styles/verification.css";
import { useNavigate } from "../hooks/navigate";
import {
  TOUR_STATIONS,
  loadTourProgress,
  isTourSealed,
  resetTourProgress,
  saveTourProgress,
  toggleStation,
  tourCompletionCount,
  type TourStation,
  type TourProgress,
} from "../ui/tour";
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
  const navigate = useNavigate();
  return (
    <article className={"tour-station" + (done ? " tour-station-done" : "")}>
      <div className="tour-seal" aria-hidden={!done}>{done ? "验" : ""}</div>
      <div className="tour-body">
        <div className="tour-chapter">{station.chapter}</div>
        <h2>{station.title}</h2>
        <div className="tour-en">{station.en}</div>
        <p className="tour-narrate">{station.narrate}</p>
        <p className="tour-task">
          <strong>行：</strong>{" "}
          {station.task}
        </p>
        <p className="tour-tip">
          <span className="tour-tip-label">授意</span>
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
            {done ? "撕掉此卷（反悔）" : "盖上此卷"}
          </Button>
        </div>
      </div>
    </article>
  );
}

export default function Tour() {
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
  const specimenSummary = `${completed} / ${TOUR_STATIONS.length} 卷已盖`;

  return (
    <div className="tour-page">
      <div className="page-head">
        <h1>巡览 <span className="tour-en">The Grand Tour of SpecProof</span></h1>
        <div className="page-sub" title="SIX SCROLLS OF ORIENTATION">
          六卷：连接 · 阅读 · 查证 · 读痕迹 · 落笔 · 盖印——每卷都是真实查验，不是指南里的第一百个链接。完成一卷盖一卷，盖完六枚，成「验讫」。
        </div>
      </div>

      <div className="tour-prologue">
        <span className="tour-prologue-mark" aria-hidden="true">序</span>
        <p>巡览不是清单，是第一夜之旅。所谓「走完巡览」——不是每一页都点过，而是每一桩真实的查验证你都被自己按了一次手印。六卷盖了五枚，你比进来的你更像验收官；盖了第六枚，章上的字便从「访客」变成「验收官」。</p>
      </div>

      {corrupted ? (
        <div className="degraded" role="status">
          <strong>本机巡览进度读不出来</strong>
          <p>localStorage 里的 specproof_tour_v1 解析失败——可能是手动改坏了，或者浏览器换了 profile。这不等于没走过：本页按全新状态呈现，旧印记已被隔离。</p>
        </div>
      ) : null}

      {saveFailed ? (
        <div className="degraded" role="status">
          <strong>盖下的印刻不进去了</strong>
          <p>本机存储被禁用（可能是无痕模式或策略）。此处的「完成」不会在刷新后保留——界面如实告诉你这一点，而不是骗你「已保存」。</p>
        </div>
      ) : null}

      <div className="tour-progress" aria-label="巡览进度">
        <div className="tour-progress-row">
          <span className="tour-progress-label">{specimenSummary}</span>
          <div className="tour-progress-rail" role="progressbar" aria-valuenow={completed} aria-valuemin={0} aria-valuemax={TOUR_STATIONS.length} aria-label="巡览完成进度">
            <div className="tour-progress-fill" style={{ width: `${(completed / TOUR_STATIONS.length) * 100}%` }} />
          </div>
        </div>
        {sealed ? (
          <div className="tour-sealed" role="status">
            <span className="tour-sealed-stamp" aria-hidden="true">验讫</span>
            <div>
              <strong>六卷齐盖，章落。</strong>
              <span>SpecProof 的史官记下了这一页——你不是本产品的访客了，而是知道这件事、做这件事、敢盖章的人。</span>
            </div>
          </div>
        ) : (
          <p className="tour-hint muted">空着的印记才有意义——每一页你盖上去，都是给自己的。</p>
        )}
      </div>

      {TOUR_STATIONS.map((st) => (
        <Station key={st.id} station={st} done={progress.completed.includes(st.id)} onToggle={() => toggle(st.id)} />
      ))}

      <div className="tour-reset-row">
        <Button size="sm" variant="ghost" onClick={reset}>
          重新巡览（擦除本机印记）
        </Button>
      </div>

      <p className="tour-colophon muted">
        巡览状态仅保存在本机 localStorage（键 <code>specproof_tour_v1</code>）；换浏览器、换电脑、换无痕窗口，一切重新走起。这不是缺陷，这是 SpecProof 的一贯性情：<strong>你的信任必须从零捡起</strong>。
      </p>
    </div>
  );
}
