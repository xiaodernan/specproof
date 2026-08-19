import { Page, expect } from "@playwright/test";

// Tenant-mode login used by every scenario with a live backend: wait for the
// auth config to reveal the credential modes, switch to the local sp_* token,
// paste it, and land in the shell. The shell only appears after the server
// accepts the token (/auth/me), so a wrong token fails here loudly.
export async function loginWithToken(page: Page, token: string): Promise<void> {
  await page.goto("/");
  await expect(page.locator(".login-modes")).toBeVisible();
  await page.getByRole("button", { name: /本地 Token/ }).click();
  await page.locator("#credential").fill(token);
  await page.getByRole("button", { name: /验证并进入 Verify/ }).click();
  await expect(page.locator(".shell")).toBeVisible();
  await expect(page.locator(".tenant-switcher")).not.toContainText("单租户 LEGACY");
}
