// Shot of the Guide page with the new "键盘与打印" callout.
const path = require("path");
const fs = require("fs");

const SHOT_DIR = "D:\\面试项目\\shots";
fs.mkdirSync(SHOT_DIR, { recursive: true });
const BASE = "http://localhost:4214/";

(async () => {
  const { chromium } = require("@playwright/test");
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(BASE + "#/guide", { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  await page.evaluate(() => {
    const el = document.querySelector(".guide-shortcuts");
    if (el) el.scrollIntoView({ block: "center" });
  });
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(SHOT_DIR, "guide-keyboard.png") });
  console.log("shot guide-keyboard.png");
  await browser.close();
  console.log("done");
})().catch((err) => {
  console.error("SHOTS FAILED:", err);
  process.exit(1);
});
