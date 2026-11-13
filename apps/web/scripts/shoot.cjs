// Screenshot harness for the aurora frontend pass (#1646/#1647).
// Writes PNGs to ../shots/ — no assertions; this is for human review.
const path = require("path");
const fs = require("fs");

const SHOT_DIR = "D:\\面试项目\\shots";
fs.mkdirSync(SHOT_DIR, { recursive: true });

(async () => {
  const { chromium } = require("@playwright/test");
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  const shots = [
    ["#/guide", "guide-dark.png"],
    ["#/login", "login-dark.png"],
    ["#/ui-kit", "ui-kit-dark.png"],
  ];

  for (const [hash, name] of shots) {
    await page.goto("http://localhost:4214/" + hash, { waitUntil: "networkidle" });
    await page.waitForTimeout(1400); // let aurora drift settle & fonts paint
    await page.screenshot({ path: path.join(SHOT_DIR, name), fullPage: false });
    console.log("shot", name);
  }

  // Shortcut overlay: open, shot, close.
  await page.goto("http://localhost:4214/#/guide", { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  await page.keyboard.press("?");
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SHOT_DIR, "shortcuts-overlay.png") });
  console.log("shot shortcuts-overlay.png");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(200);

  // Light theme
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
  await page.waitForTimeout(1300);
  await page.screenshot({ path: path.join(SHOT_DIR, "guide-light.png") });
  console.log("shot guide-light.png");

  // Mobile width
  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await mobile.goto("http://localhost:4214/#/guide", { waitUntil: "networkidle" });
  await mobile.waitForTimeout(1200);
  await mobile.screenshot({ path: path.join(SHOT_DIR, "guide-mobile.png") });
  console.log("shot guide-mobile.png");

  await browser.close();
  console.log("done");
})().catch((err) => {
  console.error("SHOTS FAILED:", err);
  process.exit(1);
});
