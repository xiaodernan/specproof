// UiKit shortcuts-section shot.
const path = require("path");
const fs = require("fs");

const SHOT_DIR = "D:\\面试项目\\shots";
fs.mkdirSync(SHOT_DIR, { recursive: true });
const BASE = "http://localhost:4214/";

(async () => {
  const { chromium } = require("@playwright/test");
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await page.goto(BASE + "#/ui-kit", { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  await page.evaluate(() => {
    const el = [...document.querySelectorAll(".ui-kit-section")].find(
      (s) => s.id === "navigation"
    );
    if (el) el.scrollIntoView({ block: "start" });
  });
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(SHOT_DIR, "ui-kit-shortcuts.png"), fullPage: false });
  console.log("shot ui-kit-shortcuts.png");
  await browser.close();
  console.log("done");
})().catch((err) => {
  console.error("SHOTS FAILED:", err);
  process.exit(1);
});
