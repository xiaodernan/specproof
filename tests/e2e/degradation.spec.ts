import { expect, test } from "@playwright/test";

// 降级 scenario: this project deliberately starts NO backend, so every API
// call through the Vite proxy fails (connection refused). The SPA must show
// graceful error notices on every surface — never a white screen.
test.describe("降级 degradation — 后端不可达时的优雅降级", () => {
  test("login page still renders without a backend", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("#welcome-title")).toContainText("需求，真的实现了吗？");
    await expect(page.locator("#credential")).toBeVisible();
  });

  test("unavailable backend keeps unverified credentials out of the workspace", async ({
    page,
  }) => {
    await page.goto("/");
    await page.locator("#credential").fill("e2e-degradation-key");
    await page.getByRole("button", { name: "连接工作区" }).click();

    await expect(page.locator(".login-card")).toBeVisible();
    await expect(page.locator(".shell")).not.toBeVisible();
    await expect(page.locator(".errorbox").first()).toBeVisible();
    await expect(page.locator(".errorbox").first()).toContainText("错误 ERROR");
    await expect(page.locator("#root")).not.toBeEmpty();
  });

  test("jobs page degrades with an error notice", async ({ page }) => {
    // Simulate an already-connected session whose backend later goes offline.
    await page.addInitScript(() => sessionStorage.setItem("specproof_api_key", "e2e-degradation-key"));
    await page.goto("/#/jobs");
    await expect(page.locator(".errorbox")).toBeVisible();
    await expect(page.locator(".errorbox")).toContainText("错误 ERROR");
    await expect(page.locator(".content")).not.toBeEmpty();
  });

  test("agent wizard still renders without a backend", async ({ page }) => {
    await page.addInitScript(() => sessionStorage.setItem("specproof_api_key", "e2e-degradation-key"));
    await page.goto("/#/agent/new");
    await expect(page.getByTestId("wizard-repo")).toBeVisible();
    await expect(page.getByText("步骤 1/4 — 目标仓库")).toBeVisible();
    await expect(page.locator("#root")).not.toBeEmpty();
  });
});
