// Print-media screenshot of the Guide page — what review receives on paper.
const path = require("path");
const fs = require("fs");

const SHOT_DIR = "D:\\面试项目\\shots";
fs.mkdirSync(SHOT_DIR, { recursive: true });
const BASE = "http://localhost:4214/";

(async () => {
  const { chromium } = require("@playwright/test");
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1100, height: 800 } });
  await page.goto(BASE + "#/guide", { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
  await page.emulateMedia({ media: "print" });
  await page.screenshot({ path: path.join(SHOT_DIR, "print-guide.png"), fullPage: true });
  console.log("shot print-guide.png");
  await page.emulateMedia({ media: "screen" });
  await browser.close();
  console.log("done");
})().catch((err) => {
  console.error("SHOTS FAILED:", err);
  process.exit(1);
});
