import { expect, test } from "@playwright/test";

/**
 * The PRINT view of the product, measured in a real browser.
 *
 * SpecProof's evidence is carried into review boards on paper. The print
 * stylesheet (apps/web/src/styles/print.css) must, in a real browser:
 *   - drop every interactive chrome surface (shell, topbar, footer);
 *   - hide the interactive buttons (a CTA on paper is dead weight);
 *   - keep the argument (the page content) at full paper width;
 *   - and NOT leak that behaviour to the screen view.
 *
 * <p>No login required: #/guide renders without a credential (the same door
 * the login page itself passes through), so the legs measure print media
 * against the product's own pages without touching the backend.</p>
 */
test("print media: chrome gone, argument full-width, screen unchanged", async ({ page }) => {
  await page.goto("/#/guide", { waitUntil: "domcontentloaded" });

  // Screen control: the shell is really there before the media switch.
  await expect(page.locator(".sidebar")).toBeVisible();
  await expect(page.locator(".workspace-topbar")).toBeVisible();

  await page.emulateMedia({ media: "print" });

  await expect(page.locator(".sidebar")).toBeHidden();
  await expect(page.locator(".workspace-topbar")).toBeHidden();
  await expect(page.locator(".workspace-footer")).toBeHidden();
  await expect(page.locator(".ui-btn").first()).toBeHidden();
  await expect(page.locator(".command-trigger")).toBeHidden();

  const contentWidth = await page
    .locator(".content")
    .evaluate((el) => el.getBoundingClientRect().width);
  const viewport = page.viewportSize();
  expect(viewport).not.toBeNull();
  expect(Math.abs(contentWidth - (viewport?.width ?? 0))).toBeLessThanOrEqual(16);

  // The media query must be scoped: resetting to screen restores the shell.
  await page.emulateMedia({ media: "screen" });
  await expect(page.locator(".sidebar")).toBeVisible();
  await expect(page.locator(".ui-btn").first()).toBeVisible();
});
