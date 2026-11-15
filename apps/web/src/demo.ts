// Demo presets for the first-run experience.
// These values match the bundled sample (demo/spring-backend + demo/requirement.txt)
// and the guide page (Guide.tsx). The demo git refs (base / head-v1) are
// created by `specproof demo` or `pwsh scripts/prepare_demo_repo.ps1`.

import { storedLocale } from "./i18n/strings";

type Locale = "zh" | "en";

export const DEMO_VERIFY = {
  repo_path: "demo/spring-backend",
  spec_path: "demo/requirement.txt",
  base_ref: "base",
  head_ref: "head-v1",
} as const;

const DEMO_VERIFY_PREPARE_NOTE_ZH =
  "首次使用先运行 `specproof demo` 或 pwsh scripts/prepare_demo_repo.ps1 为演示仓库创建 git 版本";
const DEMO_VERIFY_ABS_PATH_NOTE_ZH =
  "若执行服务运行在其他目录, 请改用 demo/spring-backend 的绝对路径。";
const DEMO_VERIFY_PREPARE_NOTE_EN =
  "On first use, run `specproof demo` or pwsh scripts/prepare_demo_repo.ps1 to prepare the demo repository";
const DEMO_VERIFY_ABS_PATH_NOTE_EN =
  "If the worker runs elsewhere, use the absolute path of demo/spring-backend instead.";

export const DEMO_VERIFY_NOTES: Record<Locale, { prepare: string; absPath: string; repo: string }> = {
  zh: {
    prepare: DEMO_VERIFY_PREPARE_NOTE_ZH,
    absPath: DEMO_VERIFY_ABS_PATH_NOTE_ZH,
    repo: DEMO_VERIFY_PREPARE_NOTE_ZH + "; " + DEMO_VERIFY_ABS_PATH_NOTE_ZH,
  },
  en: {
    prepare: DEMO_VERIFY_PREPARE_NOTE_EN,
    absPath: DEMO_VERIFY_ABS_PATH_NOTE_EN,
    repo: DEMO_VERIFY_PREPARE_NOTE_EN + "; " + DEMO_VERIFY_ABS_PATH_NOTE_EN,
  },
};

/** Locale-resolved demo notes (zh/en, read at call time). */
export function demoVerifyNotes(locale: Locale = storedLocale()) {
  return DEMO_VERIFY_NOTES[locale];
}

const DEMO_AGENT_ZH = {
  task_name: "修复 double 函数",
  spec_text:
    "修复 calc.py 中 double 函数的 bug：它目前把输入除以 2，应返回输入的两倍 (x * 2)。\n" +
    "验收: 覆盖正数、负数和零的现有测试全部通过。\n" +
    "禁止: 修改或删除测试文件。\n" +
    "影响: calc.py test_calc.py",
} as const;

const DEMO_AGENT_EN = {
  task_name: "Fix the double function",
  spec_text:
    "Fix the bug in calc.py's double function: it currently divides the input by 2; it should return twice the input (x * 2).\n" +
    "Acceptance: all existing tests covering positive, negative and zero pass.\n" +
    "Forbidden: modifying or deleting test files.\n" +
    "Scope: calc.py test_calc.py",
} as const;

export const DEMO_AGENTS: Record<Locale, { readonly task_name: string; readonly spec_text: string }> = {
  zh: DEMO_AGENT_ZH,
  en: DEMO_AGENT_EN,
};

/** Locale-resolved demo agent task (zh/en, read at call time). */
export function demoAgentSample(locale: Locale = storedLocale()) {
  return DEMO_AGENTS[locale];
}

// ── Backwards-compatible zh-first aliases (legacy call sites + tests) ──
export const DEMO_VERIFY_PREPARE_NOTE = DEMO_VERIFY_NOTES.zh.prepare;
export const DEMO_VERIFY_ABS_PATH_NOTE = DEMO_VERIFY_NOTES.zh.absPath;
export const DEMO_VERIFY_REPO_NOTE = DEMO_VERIFY_NOTES.zh.repo;
export const DEMO_AGENT = DEMO_AGENTS.zh;
