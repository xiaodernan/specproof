import { expect, test } from "@playwright/test";
import { loginWithToken } from "./helpers";

// 权限 scenario: the W37 identity UI. Admin sees the identity console and
// its management controls; a viewer principal cannot (nav hidden, deep link
// gated), while read-only surfaces keep working; unauthenticated visitors
// only ever see the login gate. The server-side RBAC is the authority — the
// UI gates are visibility-only.
test.describe("权限 permissions — W37 身份 UI: viewer vs admin", () => {
  test("admin sees the identity console and its management controls", async ({ page }) => {
    const token = process.env.E2E_ADMIN_TOKEN || "";
    const adminEmail = process.env.E2E_ADMIN_EMAIL || "";
    const viewerEmail = process.env.E2E_VIEWER_EMAIL || "";
    expect(token.length).toBeGreaterThan(0);

    await loginWithToken(page, token);
    await expect(page.locator(".nav-item", { hasText: "身份" })).toBeVisible();
    await expect(
      page.locator(".tenant-roles").getByText("admin", { exact: true })
    ).toBeVisible();

    await page.goto("/#/identity");
    await expect(page.getByText("用户管理 Users")).toBeVisible();
    await expect(page.getByText("新建用户")).toBeVisible();
    await expect(page.getByRole("button", { name: "创建 Create" })).toBeVisible();
    await expect(page.getByText(adminEmail)).toBeVisible();
    await expect(page.getByText(viewerEmail)).toBeVisible();
    await expect(page.getByTestId("identity-forbidden")).toHaveCount(0);
  });

  test("viewer cannot see admin-only controls (nav hidden, deep link gated)", async ({
    page,
  }) => {
    const token = process.env.E2E_VIEWER_TOKEN || "";
    expect(token.length).toBeGreaterThan(0);

    await loginWithToken(page, token);
    await expect(
      page.locator(".tenant-roles").getByText("viewer", { exact: true })
    ).toBeVisible();

    // With the App.tsx nav gate the sidebar entry is hidden for a known
    // non-admin/operator principal; without it, clicking the entry must
    // still land on the forbidden notice — a viewer never reaches the
    // admin controls in either configuration.
    const identityNav = page.locator(".nav-item", { hasText: "身份" });
    if ((await identityNav.count()) > 0) {
      await identityNav.first().click();
    } else {
      await page.goto("/#/identity");
    }
    await expect(page.getByTestId("identity-forbidden")).toBeVisible();
    await expect(page.getByRole("button", { name: "创建 Create" })).toHaveCount(0);
    await expect(page.getByPlaceholder("user@example.com")).toHaveCount(0);

    // A direct deep link renders the forbidden notice, never the controls.
    await page.goto("/#/identity");
    await expect(page.getByTestId("identity-forbidden")).toBeVisible();
    await expect(page.getByRole("button", { name: "创建 Create" })).toHaveCount(0);
    await expect(page.getByPlaceholder("user@example.com")).toHaveCount(0);

    // Read-only surfaces keep working for the viewer (RBAC jobs:read).
    await page.goto("/#/jobs");
    await expect(page.locator("tbody tr", { hasText: "e2e/demo-repo" })).toBeVisible();
  });

  test("unauthenticated visitor only sees the login gate", async ({ page }) => {
    await page.goto("/#/jobs");
    await expect(page.locator(".login-card")).toBeVisible();
    await expect(page.locator(".shell")).toHaveCount(0);
    await expect(page.locator(".nav-item", { hasText: "身份" })).toHaveCount(0);
  });
});
