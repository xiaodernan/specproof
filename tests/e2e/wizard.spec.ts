import { expect, test } from "@playwright/test";
import { loginWithToken } from "./helpers";

// 向导 scenario: drive the existing 4-step agent wizard (repo -> spec ->
// gates -> review) against the REAL API and land on the job detail page.
test.describe("向导 wizard — 通过 4 步向导创建 Agent 任务并到达详情页", () => {
  test("creates a job via the wizard and reaches the detail page", async ({ page }) => {
    const token = process.env.E2E_ADMIN_TOKEN || "";
    expect(token.length).toBeGreaterThan(0);
    await loginWithToken(page, token);

    // Step 1/4 — repo.
    await page.goto("/#/agent/new");
    await page.getByTestId("wizard-repo").fill("e2e/demo-repo");
    await page.getByTestId("wizard-task").fill("E2E 分页改造");
    await page.getByRole("link", { name: /下一步 Next/ }).click();
    await expect(page).toHaveURL(/#\/agent\/new\/spec/);

    // Step 2/4 — spec.
    await page
      .getByTestId("wizard-spec")
      .fill("为 /users 列表接口增加分页参数 (page, page_size), 默认 20, 上限 100, 并补充分页单测。");
    await page.getByRole("link", { name: /下一步 Next/ }).click();
    await expect(page).toHaveURL(/#\/agent\/new\/gates/);

    // Step 3/4 — gates (defaults already carry the wizard constraints).
    await page.getByRole("link", { name: /下一步 Next/ }).click();
    await expect(page).toHaveURL(/#\/agent\/new\/review/);
    await expect(page.getByText(/run_tests/).first()).toBeVisible();

    // Step 4/4 — review & submit: POST /agent/jobs then redirect to detail.
    await page.getByTestId("wizard-submit").click();
    await expect(page).toHaveURL(/#\/agent\/jobs\/[0-9a-f-]{36}/);

    // The detail page renders the created job (status timeline + spec text).
    await expect(page.locator("h1")).toContainText("E2E 分页改造");
    await expect(page.locator("h1")).toContainText("PLANNING");
    await expect(page.getByText("任务创建 Job created")).toBeVisible();
    await expect(page.getByText(/为 \/users 列表接口增加分页/)).toBeVisible();

    // The new job also shows up in the agent console list.
    await page.goto("/#/agent");
    const row = page.locator("tbody tr", { hasText: "E2E 分页改造" });
    await expect(row).toBeVisible();
    await expect(row.getByText("PLANNING", { exact: true })).toBeVisible();
  });
});
