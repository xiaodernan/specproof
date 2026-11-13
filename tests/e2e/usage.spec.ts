import { expect, test } from "@playwright/test";
import { loginWithToken } from "./helpers";

/**
 * 缓存健康 (the LLM usage ledger panel) — the front door of the honesty
 * contract: the sidebar points at the page, the page renders without
 * crashing, and whatever this environment's ledger contains is shown as-is
 * (in this sandbox .local/llm_usage.jsonl does not exist, so the honest
 * empty state is what must render — never a fabricated number, never a crash).
 */
test.describe("缓存健康 · the ledger route renders honestly", () => {
  test("navigating to 缓存健康 renders the panel or its honest empty state", async ({ page }) => {
    const token = process.env.E2E_ADMIN_TOKEN || "";
    expect(token.length).toBeGreaterThan(0);

    await loginWithToken(page, token);
    await page.goto("/#/usage", { waitUntil: "domcontentloaded" });

    // Sidebar nav item is the front door.
    await expect(page.getByRole("link", { name: "缓存健康" })).toBeVisible();

    // Either the ledger has rows (stat grid + basis note visible) or the
    // honest empty panel — both are the contract. Wait for whichever wins here.
    const stats = page.locator(".usage-basis-note");
    const empty = page.getByText(/账本尚无记录/);
    await expect(stats.or(empty).first()).toBeVisible({ timeout: 30_000 });
  });
});
