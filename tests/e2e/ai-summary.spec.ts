import { expect, test } from "@playwright/test";
import { loginWithToken } from "./helpers";

/**
 * AI 解读 (the "AI 解读本次验收" panel) — the user-facing leg that proves
 * the button is not decorative. Click it, then accept either honest outcome:
 *   - a summary renders (.ai-summary-text, provider reachable), or
 *   - an explicit error state renders with a user-facing message (503 / provider).
 * Either way, the button does not wedge into a perpetual loading state.
 *
 * The provider call is deliberately not asserted here: e2e must work with and
 * without "LLM credentials present", and in this sandbox the fixture DOES
 * inherit .local/llm.json, so the success path will actually be exercised —
 * but a CI without credentials must not turn red for an environmental reason.
 */
test.describe("AI 解读 — the button answers, or degrades honestly", () => {
  test("clicking AI 解读 renders a summary or an explicit failure state", async ({ page }) => {
    const token = process.env.E2E_ADMIN_TOKEN || "";
    const jobId = process.env.E2E_JOB_ID || "";
    expect(token.length).toBeGreaterThan(0);
    expect(jobId.length).toBeGreaterThan(0);

    await loginWithToken(page, token);
    await page.goto("/#/jobs/" + encodeURIComponent(jobId), { waitUntil: "domcontentloaded" });

    // The button label is literal; there is exactly one per verdict panel.
    const aiBtn = page.getByRole("button", { name: "AI 解读本次验收" });
    await expect(aiBtn).toBeVisible();
    await aiBtn.click();

    // Either the summary lands, or the failure box renders — both are the
    // honest contract. Wait for whichever wins this run.
    const summary = page.locator(".ai-summary-text");
    const failure = page.locator(".errorbox, [role=alert]");
    await expect(
      summary.or(failure).first()
    ).toBeVisible({ timeout: 45_000 });

    // The button must still be present and labelled — not silently vanished.
    await expect(page.getByRole("button", { name: "重新解读" })).toBeVisible();
  });
});
