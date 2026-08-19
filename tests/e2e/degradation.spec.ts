import { expect, test } from "@playwright/test";

// 降级 scenario: this project deliberately starts NO backend, so every API
// call through the Vite proxy fails (connection refused). The SPA must show
// graceful error notices on every surface — never a white screen.
test.describe("降级 degradation — 后端不可达时的优雅降级", () => {
  test("login page still renders without a backend", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".login-card h1")).toHaveText("SpecProof Control Room");
    await expect(page.locator("#credential")).toBeVisible();
  });

  test("shell + dashboard show a graceful error notice, no white screen", async ({
    page,
  }) => {
    await page.goto("/");
    await page.locator("#credential").fill("e2e-degradation-key");
    await page.getByRole("button", { name: "连接 Connect" }).click();

    // The shell itself survives; the dashboard reports the failure.
    await expect(page.locator(".shell")).toBeVisible();
    await expect(page.locator(".brand-name")).toHaveText("SpecProof");
    await expect(page.getByTestId("errorbox").first()).toBeVisible();
    await expect(page.getByTestId("errorbox").first()).toContainText("错误 ERROR");
    await expect(page.locator("#root")).not.toBeEmpty();
  });

  test("jobs page degrades with an error notice", async ({ page }) => {
    await page.goto("/");
    await page.locator("#credential").fill("e2e-degradation-key");
    await page.getByRole("button", { name: "连接 Connect" }).click();
    await expect(page.locator(".shell")).toBeVisible();

    await page.goto("/#/jobs");
    await expect(page.getByTestId("errorbox")).toBeVisible();
    await expect(page.getByTestId("errorbox")).toContainText("错误 ERROR");
    await expect(page.locator(".content")).not.toBeEmpty();
  });

  test("agent wizard still renders without a backend", async ({ page }) => {
    await page.goto("/");
    await page.locator("#credential").fill("e2e-degradation-key");
    await page.getByRole("button", { name: "连接 Connect" }).click();
    await expect(page.locator(".shell")).toBeVisible();

    await page.goto("/#/agent/new");
    await expect(page.getByTestId("wizard-repo")).toBeVisible();
    await expect(page.getByText("步骤 1/4 — 目标仓库")).toBeVisible();
    await expect(page.locator("#root")).not.toBeEmpty();
  });
});
