import { expect, test } from "@playwright/test";
import { loginWithToken } from "./helpers";

// 向导 scenario: drive the existing 3-step agent wizard (repo -> spec ->
// review) against the REAL API and land on the job detail page.
//
// It was a FOUR-step wizard (repo -> spec -> gates -> review) until the
// "gates" step was removed: that step had no editable control at all (the
// budget and the step count are server-side environment settings), so the
// user could only click "Next" and go around in circles. Its honest
// explanation was folded into the review step, which is what this scenario
// now asserts.
test.describe("向导 wizard — 通过 3 步向导创建 Agent 任务并到达详情页", () => {
  test("creates a job via the wizard and reaches the detail page", async ({ page }) => {
    const token = process.env.E2E_ADMIN_TOKEN || "";
    expect(token.length).toBeGreaterThan(0);
    await loginWithToken(page, token);

    // Step 1/3 — repo.
    await page.goto("/#/agent/new");
    await page.getByTestId("wizard-repo").fill("e2e/demo-repo");
    await page.getByTestId("wizard-task").fill("E2E 分页改造");
    await page.getByRole("link", { name: /下一步 Next/ }).click();
    await expect(page).toHaveURL(/#\/agent\/new\/spec/);

    // Step 2/3 — spec.
    await page
      .getByTestId("wizard-spec")
      .fill("为 /users 列表接口增加分页参数 (page, page_size), 默认 20, 上限 100, 并补充分页单测。");
    await page.getByRole("link", { name: /下一步 Next/ }).click();
    await expect(page).toHaveURL(/#\/agent\/new\/review/);

    // Step 3/3 — review & submit. The review step carries the honest
    // statement the old gates step used to hold: the executor runs the
    // checks that apply to the project and lists pass/fail/skip for each,
    // and the budget is the server's to decide -- there is no switch here.
    await expect(
      page.getByText(/运行预算与最大步数由服务端配置决定/),
    ).toBeVisible();
    await expect(page.getByText(/未执行的检查不算通过/)).toBeVisible();

    // Submit: POST /agent/jobs then redirect to detail.
    await page.getByTestId("wizard-submit").click();
    await expect(page).toHaveURL(/#\/agent\/jobs\/[0-9a-f-]{36}/);

    // The detail page renders the created job (status timeline + spec text).
    await expect(page.locator("h1")).toContainText("E2E 分页改造");
    // The status pill keeps the RAW console token in its title attribute and
    // shows the human label as its text. Which token it is depends on the
    // environment (with no LLM configured the plan fails honestly, so it
    // ends FAILED), so the assertion is the vocabulary: the job reached a
    // state the console knows, not a token nobody can interpret.
    const statusToken = await page.locator("h1 .pill").getAttribute("title");
    expect(
      ["PLANNING", "AWAITING_APPROVAL", "EXECUTING", "COMPLETED", "FAILED", "CANCELLED"],
      "the console status token: " + String(statusToken),
    ).toContain(statusToken);
    await expect(page.getByText("任务创建 Job created")).toBeVisible();
    await expect(page.getByText(/为 \/users 列表接口增加分页/)).toBeVisible();

    // The new job also shows up in the agent console list.
    await page.goto("/#/agent");
    const row = page.locator("tbody tr", { hasText: "E2E 分页改造" });
    await expect(row).toBeVisible();
    // The list shows the human label; the raw console token lives in the
    // pill's title attribute. Which token it is depends on the environment
    // (no LLM configured -> the plan fails honestly), so the assertion is
    // the vocabulary, not one token.
    const rowStatus = await row.locator(".pill").getAttribute("title");
    expect(
      ["PLANNING", "AWAITING_APPROVAL", "EXECUTING", "COMPLETED", "FAILED", "CANCELLED"],
      "the console status token in the list: " + String(rowStatus),
    ).toContain(rowStatus);
  });
});
