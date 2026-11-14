import type { Locale } from "../i18n/strings";

/**
 * The Fourteen Gestures — the officer's fourteen ways of standing before
 * evidence. Each maps one face to one verdict token. This table is the
 * productised embodiment of `docs/world/SPECROOF_WORLD.md` Appendix C;
 * the tokens referenced here are the report verdicts the product actually
 * emits (`apps/web/src/ui/verdict.ts`).
 */

export interface GestureFace {
  id: string;
  numeral: string;
  /** One-word face name. */
  zhName: string;
  enName: string;
  /** The report verdict this gesture corresponds to. */
  token: string;
  /** One line on the face — what it looks like at the moment you see it. */
  face: Record<Locale, string>;
  /** What you do, and what it means in iron-evidence terms. */
  act: Record<Locale, string>;
  /** Which real route in the product shows this gesture's evidence. */
  route: string;
  routeLabel: Record<Locale, string>;
}

export const GESTURES: GestureFace[] = [
  {
    id: "stare",
    numeral: "一",
    zhName: "直视",
    enName: "The Look",
    token: "VERIFIED",
    face: { zh: "印章盖下去的正脸", en: "The face the seal lands on" },
    act: { zh: "盖印完事——基线过了、头版本也挂了，铁证如此。这不是聊天，这是证据。", en: "Stamp it and be done — the baseline failed, the head failed; the iron evidence says so. Not a chat; a fact." },
    route: "#/explorer",
    routeLabel: { zh: "看看案件档案里的红印", en: "See the sealed case file" },
  },
  {
    id: "provoke",
    numeral: "二",
    zhName: "挑衅",
    enName: "The Challenge",
    token: "BLOCKED",
    face: { zh: "眉毛线性推开，嘴角收紧", en: "Brows pushed apart, corners of the mouth held tight" },
    act: { zh: "铁证钉在铁门上：base_pass_head_fail——改前通过、改后失败。不需要协商。", en: "Iron evidence nailed to the iron gate: base_pass_head_fail — passing before, failing after. No negotiation." },
    route: "#/matrix",
    routeLabel: { zh: "去矩阵找那行铁", en: "Go find the iron row in the matrix" },
  },
  {
    id: "probe",
    numeral: "三",
    zhName: "试探",
    enName: "The Probe",
    token: "NEEDS_REVIEW",
    face: { zh: "眼角微敛，笔含在指尖", en: "Corner of the eye slightly narrowed, pen held in the fingertips" },
    act: { zh: "证据还没站稳——人必须进来看一眼：不能放过，也不能错杀。", en: "The evidence has not yet stood firm — a human must step in: not to acquit, but not to condemn wrongly." },
    route: "#/matrix",
    routeLabel: { zh: "逐项查看未确认的验收条件", en: "Review the unverified conditions" },
  },
  {
    id: "gaze",
    numeral: "四",
    zhName: "远眺",
    enName: "The Far Gaze",
    token: "STALE",
    face: { zh: "头顶出鞘，鹅颈侧耳", en: "Neck stretched, goose-necked ear" },
    act: { zh: "太久没验了。那份结论只是历史——重跑一遍再说话。", en: "Too stale to be trusted. That verdict is history — re-run, then speak." },
    route: "#/jobs",
    routeLabel: { zh: "看看哪些旧作业还没复验", en: "See which stale job wants a re-run" },
  },
  {
    id: "coldsmile",
    numeral: "五",
    zhName: "冷笑",
    enName: "The Cold Smile",
    token: "CANCELLED",
    face: { zh: "脸颊收紧，下颌咬上", en: "Cheeks gathered, jaw set" },
    act: { zh: "提交的人撤回了。铁证还留着，但顺序已经空了——归档，不对账。", en: "The author withdrew. The iron evidence remains, but the order is empty — file it away; nothing to audit against." },
    route: "#/audit",
    routeLabel: { zh: "看看审计轨迹里的取消记录", en: "See the cancellation in the audit trail" },
  },
  {
    id: "irondoor",
    numeral: "六",
    zhName: "关门",
    enName: "The Iron Door",
    token: "ERROR",
    face: { zh: "有人来拉门却拉不动", en: "Someone pulls; the door will not move" },
    act: { zh: "门自己关了。执行错误——先把门打开，再谈判决。", en: "The door closed by itself. An execution error — open the gate first, then judge." },
    route: "#/health",
    routeLabel: { zh: "先确认服务是可达的", en: "Check whether the service is actually up" },
  },
  {
    id: "silentwrite",
    numeral: "七",
    zhName: "默书",
    enName: "The Silent Pen",
    token: "FAILED",
    face: { zh: "这一百行进入了你的肌肉记忆", en: "A hundred lines enter your muscle memory" },
    act: { zh: "执行未果。不是结论错，是路没走完——查执行错误，再跑。", en: "The run did not finish. Not a wrong verdict — an unfinished one. Read the execution error, then re-run." },
    route: "#/jobs",
    routeLabel: { zh: "看看执行记录里失败的原因", en: "Read the failure in the execution record" },
  },
  {
    id: "waveaway",
    numeral: "八",
    zhName: "挥去",
    enName: "The Waved Hand",
    token: "EXPIRED",
    face: { zh: "一巴掌挥走了保质期", en: "A hand wave that ages out" },
    act: { zh: "验证过了，但过了保质期。重新验，不要重复念旧账。", en: "It was once verified, and now it is expired. Re-verify — do not recite the past." },
    route: "#/jobs",
    routeLabel: { zh: "看看哪些已临期", en: "See which are about to expire" },
  },
  {
    id: "annotate",
    numeral: "九",
    zhName: "批阅",
    enName: "The Annotation",
    token: "VERIFIED",
    face: { zh: "读完了，顶上又盖一枚小章", en: "Read; a small stamp lands on top" },
    act: { zh: "验收通过之后还要批阅——读者确认读过、认下。", en: "After verification comes annotation — the reader signs that they read and accepted." },
    route: "#/jobs",
    routeLabel: { zh: "给某次验收盖个批阅", en: "Annotate one verification" },
  },
  {
    id: "forgive",
    numeral: "十",
    zhName: "原谅",
    enName: "The Mercy",
    token: "NEEDS_REVIEW",
    face: { zh: "关灯那把钥匙被交回你手里", en: "The key to the dark is handed back to you" },
    act: { zh: "你可以再看一遍。验收官允许再一次——但不允许没有代价地再一次。", en: "One more look is permitted. The officer permits asking again — never for nothing." },
    route: "#/matrix",
    routeLabel: { zh: "回矩阵挑一行再看一次", en: "Back to the matrix for one more look" },
  },
  {
    id: "pushdoor",
    numeral: "十一",
    zhName: "推开",
    enName: "The Gentle Push",
    token: "ERROR",
    face: { zh: "门轻推一点，它自己停了", en: "A gentle push; it stops itself" },
    act: { zh: "推门，门不会动——因为门是它自己关的。不找人，先看 error。", en: "Push the door; it will not move — because the door shut itself. No scapegoat; read the error first." },
    route: "#/health",
    routeLabel: { zh: "健康页先看看 503 从哪来", en: "Check the health page for 503s" },
  },
  {
    id: "lightsoff",
    numeral: "十二",
    zhName: "关灯",
    enName: "Lights Off",
    token: "FAILED",
    face: { zh: "今晚不开了", en: "Not tonight" },
    act: { zh: "这晚不继续了：先停，修，再亮灯。不要靠想象把路走完。", en: "This night ends. Stop, fix, then relight — do not walk the road by imagination." },
    route: "#/jobs",
    routeLabel: { zh: "去看看失败了的那条", en: "Find the one that failed" },
  },
  {
    id: "laydown",
    numeral: "十三",
    zhName: "放下笔",
    enName: "Set Down the Pen",
    token: "VERIFIED",
    face: { zh: "桌子空了，没有人敲你", en: "The desk is clear; nobody knocks" },
    act: { zh: "案子结了。VERIFIED 落定，你不需要再回头看一眼这个结论。", en: "The case is closed. VERIFIED landed; no need to glance at this verdict again." },
    route: "#/explorer",
    routeLabel: { zh: "去案件档案翻那一页", en: "Go read the case file page" },
  },
  {
    id: "stillalive",
    numeral: "十四",
    zhName: "仍活着",
    enName: "Still Alive",
    token: "STALE",
    face: { zh: "没人问它，火还燃着", en: "Nobody asks; the fire still burns" },
    act: { zh: "没人处理，不等于它死了。只是快过期了——重跑再见。", en: "Nobody handles it, which does not mean it is dead. It is nearing expiry — re-run and we will see." },
    route: "#/jobs",
    routeLabel: { zh: "去看看哪些快过期了", en: "Find the ones about to expire" },
  },
];
