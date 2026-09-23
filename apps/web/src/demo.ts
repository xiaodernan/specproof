// Demo presets for the first-run experience.
// These values match the bundled sample (demo/spring-backend + demo/requirement.txt)
// and the guide page (Guide.tsx). The demo git refs (base / head-v1) are
// created by `specproof demo` or `pwsh scripts/prepare_demo_repo.ps1`.

export const DEMO_VERIFY = {
  repo_path: "demo/spring-backend",
  spec_path: "demo/requirement.txt",
  base_ref: "base",
  head_ref: "head-v1",
} as const;

// The first-run note is two independent sentences that different pages show in
// different ways: NewVerification renders the full text, while Guide shows only
// the "use an absolute path" follow-up inline after its own lead-in. Keep them
// as named parts (composed into the full note) instead of `split()`-ing the
// string at render time — rephrasing one sentence must never silently drop the
// other from the UI.
export const DEMO_VERIFY_PREPARE_NOTE =
  "首次使用先运行 `specproof demo` 或 pwsh scripts/prepare_demo_repo.ps1 为演示仓库创建 git 版本";
export const DEMO_VERIFY_ABS_PATH_NOTE =
  "若执行服务运行在其他目录, 请改用 demo/spring-backend 的绝对路径。";
export const DEMO_VERIFY_REPO_NOTE =
  DEMO_VERIFY_PREPARE_NOTE + "; " + DEMO_VERIFY_ABS_PATH_NOTE;

export const DEMO_AGENT = {
  task_name: "修复 double 函数",
  spec_text:
    "修复 calc.py 中 double 函数的 bug：它目前把输入除以 2，应返回输入的两倍 (x * 2)。\n" +
    "验收: 覆盖正数、负数和零的现有测试全部通过。\n" +
    "禁止: 修改或删除测试文件。\n" +
    "影响: calc.py test_calc.py",
} as const;
