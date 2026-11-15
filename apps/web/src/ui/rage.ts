/**
 * Rage hints — turning this browser's real rage-taps into concrete coaching.
 *
 * The signatures come from `specproof_heat_v1` (see telemetry/behavior.ts):
 * same element, tag.class|first-24-chars of text, 3+ taps inside 2 seconds.
 * This module maps those signatures to the exact next step a newcomer
 * would want instead of tapping harder. Pure functions, no storage reads.
 */

import type { Locale } from "../i18n";

export type RageHint = {
  key: string;
  title: Record<Locale, string>;
  body: Record<Locale, string>;
};

type Rule = {
  match: RegExp;
  hint: RageHint;
};

const RULES: Rule[] = [
  {
    match: /approve|approv|批\s*准|盖\s*章|签\s*字/i,
    hint: {
      key: "approve",
      title: { zh: "批准永远是真人一键", en: "Approve is always a human click" },
      body: {
        zh: "这个按钮旁边就是证据和抉择记录——先点开证据面板，看完再批。系统不会替你盖章，见过的争议都来自「先点批准再补证据」。",
        en: "The evidence and the decision trail live right next to this button — open the evidence pane first. The system never seals on your behalf; every dispute starts with sealing before reading.",
      },
    },
  },
  {
    match: /seal|盖印|第.*印|tour|巡览/i,
    hint: {
      key: "tour-seal",
      title: { zh: "盖印前先真正到站", en: "Visit the station before it can be sealed" },
      body: {
        zh: "六枚印的规则改过：没打开过那一页，印章就是灰的。先点顶部「六站巡览」走完该站，倒计时无关紧要——去看一次就盖得了。",
        en: "The rule changed: no page visited, no seal. Grey means unread. Open the tour once, actually look at the station, and the seal un-greys — no timers involved.",
      },
    },
  },
  {
    match: /run|verify|verif|执行|验收|运行/i,
    hint: {
      key: "run",
      title: { zh: "先读证据，再点执行", en: "Read evidence, then run" },
      body: {
        zh: "执行按钮下面有 base 与 head 两份验收报告模板——先切到「证据」标签页看一眼两边的差异，再回来按执行。白敲三次的结果还是白敲三次。",
        en: "Below this button live the two report templates — base and head. Peek at the Evidence tab first, then come back and run. Three blind taps are three blind taps.",
      },
    },
  },
  {
    match: /jobs\/new|新建|new verification|创建/i,
    hint: {
      key: "new-verification",
      title: { zh: "新建验证要三件套", en: "Three things open a verification" },
      body: {
        zh: "仓库路径、base/head 引用、需求文件——少一件表单就不让你点下去。页面顶部有一键示例，先点「加载演示数据」看看完整长啥样。",
        en: "Repo path, base/head refs, one requirements file — the form refuses otherwise. At the top there is a “load demo data” button, take one minute to see the whole shape first.",
      },
    },
  },
  {
    match: /model|provider|settings|模型|设置|连接/i,
    hint: {
      key: "model-path",
      title: { zh: "模型设置失败多半是这一处", en: "Model setup usually trips on this one" },
      body: {
        zh: "地址要带 /v1 后缀（例如 https://…/v1）；模型名 gpt-6-sol 不要拼错；协议选 responses 或 chat 之一。任何一步不对，测试按钮会立刻回吐具体错字。",
        en: "Keep the address with a /v1 suffix; the model is gpt-6-sol, spelled exactly; protocol is either responses or chat. If anything is off, the test button quotes the exact typo back.",
      },
    },
  },
];

const GENERIC: RageHint = {
  key: "generic",
  title: { zh: "这里在本机让你急过", en: "This spot made you impatient here" },
  body: {
    zh: "本机气候图记录：这个位置被同一只浏览器连续重敲。通常它下面藏着一句说明——按 H 打开教学模式，同一个位置上金色徽章就是它。",
    en: "This browser hammered this exact control repeatedly. Usually a hint is hiding right under it — press H to arm the teaching layer and read the gold badge anchored here.",
  },
};

export function hintForRage(target: string): RageHint {
  for (const rule of RULES) {
    if (rule.match.test(target)) return rule.hint;
  }
  return GENERIC;
}

/** Collapse raw rage entries into at most `max` distinct hints, most-raged first. */
export function hintsForRage(
  rageTop: readonly { target: string; count: number }[],
  max = 2,
): (RageHint & { count: number })[] {
  const out: (RageHint & { count: number })[] = [];
  const seen = new Set<string>();
  for (const entry of rageTop) {
    const hint = hintForRage(entry.target);
    if (seen.has(hint.key)) {
      const existing = out.find((h) => h.key === hint.key);
      if (existing) existing.count += entry.count;
      continue;
    }
    seen.add(hint.key);
    out.push({ ...hint, count: entry.count });
    if (out.length >= max) break;
  }
  return out;
}
