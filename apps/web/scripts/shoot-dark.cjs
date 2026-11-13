// Dark-theme screenshots for the aurora pass. Sets specproof_theme=dark
// before the SPA boots (localStorage), so the aurora mesh is actually the ink.
const path = require("path");
const fs = require("fs");

const SHOT_DIR = "D:\\面试项目\\shots";
fs.mkdirSync(SHOT_DIR, { recursive: true });
const BASE = "http://localhost:4214/";

(async () => {
  const { chromium } = require("@playwright/test");
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => {
    try { window.localStorage.setItem("specproof_theme", "dark"); } catch (_) {}
  });
  const page = await ctx.newPage();

  const shots = [
    ["#/guide", "aurora-guide-dark.png"],
    ["#/login", "aurora-login-dark.png"],
    ["#/ui-kit", "aurora-ui-kit-dark.png"],
  ];
  for (const [hash, name] of shots) {
    await page.goto(BASE + hash, { waitUntil: "networkidle" });
    await page.waitForTimeout(1600);
    await page.screenshot({ path: path.join(SHOT_DIR, name) });
    console.log("shot", name);
  }

  await page.goto(BASE + "#/guide", { waitUntil: "networkidle" });
  await page.waitForTimeout(900);
  await page.keyboard.press("?");
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SHOT_DIR, "aurora-shortcuts-dark.png") });
  console.log("shot aurora-shortcuts-dark.png");

  await browser.close();
  console.log("done");
})().catch((err) => {
  console.error("SHOTS FAILED:", err);
  process.exit(1);
});
