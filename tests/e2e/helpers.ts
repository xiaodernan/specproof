import { Page, expect } from "@playwright/test";

// Tenant-mode login used by every scenario with a live backend: wait for the
// auth config to reveal the credential modes, switch to the local sp_* token,
// paste it, and land in the shell. The shell only appears after the server
// accepts the token (/auth/me), so a wrong token fails here loudly.
export async function loginWithToken(page: Page, token: string): Promise<void> {
  // Measured 2026-09-29 on a loaded machine (a parallel full pytest gate was
  // running): the default `load` wait blew the 60s test budget on Vite's first
  // on-demand transform of the SPA, and the failure looked like "the app never
  // served a login page". `domcontentloaded` is the honest wait here: the next
  // line is itself an explicit visibility expectation with its own timeout, and
  // the shell only appears after /auth/me answers, so nothing is being skipped.
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".login-modes")).toBeVisible();
  await page.getByRole("button", { name: "访问令牌", exact: true }).click();
  await page.locator("#credential").fill(token);
  await page.getByRole("button", { name: "连接工作区", exact: true }).click();
  await expect(page.locator(".shell")).toBeVisible();
  await expect(page.locator(".tenant-switcher")).not.toContainText("单租户 LEGACY");
}
