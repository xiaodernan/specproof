/**
 * 巡览 · The Grand Tour — SpecProof 的自游路牌状态机。
 *
 * 每一卷都是一桩真实的查验：目标指向本产品的真实页面，完成由手触按钮核对，
 * 不抓 API 冒充检测，也不空编造进度。进度存本机 localStorage（`specproof_tour_v1`），
 * 键名如实说明——换浏览器、换设备，一切从头开始，不说"保存云端了"。
 */

export type TourStationId =
  | "gate"
  | "verdict"
  | "matrix"
  | "findings"
  | "epic"
  | "seal";

export interface TourStation {
  id: TourStationId;
  numeral: string;
  title: string;
  en: string;
  chapter: string;
  narrate: string;
  task: string;
  tip: string;
  route: string;
  routeLabel: string;
}

export interface TourProgress {
  completed: TourStationId[];
  completed_at: Partial<Record<TourStationId, string>>;
  sealed_at: string | null;
}

export const TOUR_STATIONS: TourStation[] = [
  {
    id: "gate",
    numeral: "一",
    title: "门 · 你推开 SpecProof 的门",
    en: "THE GATE",
    chapter: "卷之一 · 抵达",
    narrate:
      "SpecProof 不在乎你写过几行代码——它等你把门打开。验收官最尊重的，是证据；不先戴上证据的目镜，不许进去",
    task: "连接工作区：用访问令牌（sp_*）或者等同事发的令牌登进来",
    tip: "没有令牌？找管理员要一份。令牌只在本浏览器的 sessionStorage 里，不上传。",
    route: "#/",
    routeLabel: "前往登录",
  },
  {
    id: "verdict",
    numeral: "二",
    title: "验 · 第一桩变更的验收报告",
    en: "THE VERDICT",
    chapter: "卷之二 · 读案",
    narrate:
      "你站在第一份验收报告前。Verdict、矩阵、证据——每一块 StatCard 都在问：你真的看进去了吗？",
    task: "打开任意 #/jobs/{id}，把「验证结论 / 验收条件 / 未通过数 / 未验证数」四块卡片逐字读一遍",
    tip: "点开「执行进度」页签看阶段时间线——每一条时间戳都不伪造。",
    route: "#/jobs",
    routeLabel: "前往变更验收列表",
  },
  {
    id: "matrix",
    numeral: "三",
    title: "山 · 铁证如山矩阵",
    en: "THE MATRIX",
    chapter: "卷之三 · 读证",
    narrate:
      "矩阵是 SpecProof 的山顶。每一行一桩证据：谁是铁、谁是静、谁是半信半疑——不读矩阵，你永远在" + 
      "看一张漂亮的截图。",
    task: "打开 #/matrix，随便翻一行，问自己：证据方式是什么？是 base_pass_head_fail 这种铁，还是 static_analysis 这种「可能对」？",
    tip: "在矩阵里点开一行 findings 细节的链接，把证据类型的中文释义读一遍。",
    route: "#/matrix",
    routeLabel: "前往矩阵",
  },
  {
    id: "findings",
    numeral: "四",
    title: "府 · 发现里的门道",
    en: "THE DISCOVERY",
    chapter: "卷之四 · 读痕迹",
    narrate:
      "每个 finding 都是一块化石：它留下了问题的痕迹、受影响的位置、以及如何在基线／头版之间翻脸。",
    task: "打开任意 #/jobs/{id} → 风险发现页签，点开任意一个 finding：severity 是 BLOCKER 吗？evidence_type 读出来像铁还是像纸？",
    tip: "点开「复制 Markdown 摘要」→ 粘贴到任意文本编辑器里看看它长什么样——评审官就是这么读的。",
    route: "#/jobs",
    routeLabel: "前往变更验收列表",
  },
  {
    id: "epic",
    numeral: "五",
    title: "史 · 落笔成卷",
    en: "THE CHRONICLER",
    chapter: "卷之五 · 读卷",
    narrate:
      "史官只把真的事情写进史册。SpecProof 把所有真实发生过的过程钉在 ledger 里，你读任意一卷，都能在 git log 里对上。",
    task: "打开 #/epic，读任意一卷：史官细则里的提交号，能否在 git log 里找到？（不能找到就来找我，我错了就改）",
    tip: "史官最爱的是细节数字——比如 `96.5%` 命中率、`2272` 字节前缀——每一位都落在 git 里。",
    route: "#/epic",
    routeLabel: "前往史诗页",
  },
  {
    id: "seal",
    numeral: "六",
    title: "印 · 盖验讫章",
    en: "THE SEAL",
    chapter: "卷之六 · 盖印",
    narrate:
      "巡览至此，你不是访客了。验收官的职业是先怀疑、后信任；而你已经走完了第一趟怀疑——把这枚印盖在名字上吧。",
    task: "在任意验收页点「复制史诗纪要」，粘贴给你自己——然后回到本页盖下最后一枚印。",
    tip: "这枚印只刻在本机 localStorage 里；换浏览器，巡览重走。信任就是这样一点一点换来的。",
    route: "#/epic",
    routeLabel: "前往史诗页",
  },
];

const KEY = "specproof_tour_v1";

const defaultProgress = (): TourProgress => ({
  completed: [],
  completed_at: {},
  sealed_at: null,
});

export function loadTourProgress(): { progress: TourProgress; corrupted: boolean } {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return { progress: defaultProgress(), corrupted: false };
    const parsed = JSON.parse(raw) as Partial<TourProgress> | null;
    if (!parsed || typeof parsed !== "object") return { progress: defaultProgress(), corrupted: true };
    const completed = Array.isArray(parsed.completed) ? parsed.completed.filter((s): s is TourStationId => TOUR_STATIONS.some((t) => t.id === s)) : [];
    const completed_at = typeof parsed.completed_at === "object" && parsed.completed_at !== null ? parsed.completed_at : {};
    const sealed_at = typeof parsed.sealed_at === "string" ? parsed.sealed_at : null;
    return { progress: { completed, completed_at, sealed_at }, corrupted: false };
  } catch {
    return { progress: defaultProgress(), corrupted: true };
  }
}

export function saveTourProgress(progress: TourProgress): boolean {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(progress));
    return true;
  } catch {
    return false;
  }
}

export function toggleStation(progress: TourProgress, id: TourStationId): TourProgress {
  const isDone = progress.completed.includes(id);
  if (isDone) {
    const completed = progress.completed.filter((s) => s !== id);
    const { [id]: _drop, ...rest } = progress.completed_at;
    const sealed_at = completed.length === TOUR_STATIONS.length ? progress.sealed_at : null;
    return { completed, completed_at: rest, sealed_at };
  }
  const completed = [...progress.completed, id];
  const completed_at = { ...progress.completed_at, [id]: new Date().toISOString() };
  const sealed_at = completed.length === TOUR_STATIONS.length ? new Date().toISOString() : progress.sealed_at;
  return { completed, completed_at, sealed_at };
}

export function resetTourProgress(): TourProgress {
  const fresh = defaultProgress();
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    /* no-op */
  }
  return fresh;
}

export function tourCompletionCount(progress: TourProgress): number {
  return progress.completed.length;
}

export function isTourSealed(progress: TourProgress): boolean {
  return progress.completed.length === TOUR_STATIONS.length;
}
