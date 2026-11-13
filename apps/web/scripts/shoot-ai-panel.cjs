// Screenshot the AI 解读 panel with a real login (mirror of e2e helpers).
const path = require("path");
const fs = require("fs");

const SHOT_DIR = "D:\\面试项目\\shots";
fs.mkdirSync(SHOT_DIR, { recursive: true });
const STATE = JSON.parse(
  fs.readFileSync(
    "D:\\面试项目\\specproof-reference\\tests\\e2e\\.state\\e2e-state.json",
    "utf8"
  )
);

(async () => {
  const { chromium } = require("@playwright/test");
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1500, height: 950 } });

  // login exactly like the e2e harness does
  await page.goto("http://127.0.0.1:5174/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "访问令牌", exact: true }).click();
  await page.locator("#credential").fill(STATE.admin_token);
  await page.getByRole("button", { name: "连接工作区", exact: true }).click();
  await page.locator(".shell").waitFor({ state: "visible", timeout: 30_000 });

  await page.goto("http://127.0.0.1:5174/#/jobs/" + encodeURIComponent(STATE.job_id), {
    waitUntil: "domcontentloaded",
  });
  await page.waitForTimeout(2500);

  const aiBtn = page.getByRole("button", { name: "AI 解读本次验收" });
  if ((await aiBtn.count()) === 0) {
    await page.screenshot({ path: path.join(SHOT_DIR, "jobdetail-no-button.png") });
    console.log("AI 解读 button not visible; shot jobdetail-no-button.png");
    await browser.close();
    return;
  }
  await aiBtn.click();
  await page.waitForTimeout(26000);

  await page.evaluate(() => {
    const panels = [...document.querySelectorAll(".panel")];
    const ai = panels.find((p) => /AI 解读/.test(p.textContent || ""));
    if (ai) ai.scrollIntoView({ block: "center" });
  });
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(SHOT_DIR, "jobdetail-ai-panel.png") });
  console.log("shot jobdetail-ai-panel.png");
  await browser.close();
  console.log("done");
})().catch((err) => {
  console.error("SHOTS FAILED:", err);
  process.exit(1);
});
