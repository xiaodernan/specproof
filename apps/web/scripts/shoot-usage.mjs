import { chromium } from "@playwright/test";
import fs from "fs";

const SHOT_DIR = "D:\\面试项目\\shots";

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1500, height: 1250 } });

  await page.addInitScript(() => {
    try {
      window.sessionStorage.setItem("specproof_api_key", "specproof-local-demo-key");
    } catch {
      // fall back to the login screen — the shot will show what a reviewer sees
    }
  });

  await page.goto("http://127.0.0.1:5174/#/usage", { waitUntil: "domcontentloaded" });
  // wait until the ledger has actually loaded (stat grid rendered), not a fixed sleep
  await page.locator(".usage-basis-note").waitFor({ state: "visible", timeout: 45_000 });
  await page.waitForTimeout(600);

  await page.screenshot({ path: SHOT_DIR + "\\usage-page.png", fullPage: true });
  console.log("shot usage-page.png");

  const btn = page.getByRole("button", { name: "7 天", exact: true });
  await btn.click();
  await page.locator(".usage-basis-note").waitFor({ state: "visible", timeout: 20_000 });
  await page.waitForTimeout(900);
  await page.screenshot({ path: SHOT_DIR + "\\usage-page-7d.png", fullPage: true });
  console.log("shot usage-page-7d.png");

  await browser.close();
  console.log("done");
})().catch((err) => {
  console.error("SHOTS FAILED:", err);
  process.exit(1);
});
