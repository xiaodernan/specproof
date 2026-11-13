// Screenshot the JobDetail AI 解读 panel against the seeded fixture job.
const path = require("path");
const fs = require("fs");

const SHOT_DIR = "D:\\面试项目\\shots";
fs.mkdirSync(SHOT_DIR, { recursive: true });
const BASE = "http://localhost:4214/";
const STATE = JSON.parse(
  fs.readFileSync(
    "D:\\面试项目\\specproof-reference\\tests\\e2e\\.state\\e2e-state.json",
    "utf8"
  )
);

(async () => {
  const { chromium } = require("@playwright/test");
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await ctx.addInitScript(
    ({ token }) => {
      try {
        window.localStorage.setItem("specproof_api_key", token);
        window.localStorage.setItem("specproof_theme", "dark");
      } catch (_) {}
    },
    { token: STATE.admin_token }
  );
  const page = await ctx.newPage();
  await page.goto(BASE + "#/jobs/" + encodeURIComponent(STATE.job_id), {
    waitUntil: "networkidle",
  });
  await page.waitForTimeout(2000);

  // click the AI 解读 button
  const aiBtn = page.getByRole("button", { name: /AI 解读本次验收/ });
  if ((await aiBtn.count()) > 0) {
    await aiBtn.first().click();
    await page.waitForTimeout(16000);
  } else {
    console.log("AI 解读 button not visible — saving raw page shot instead");
  }
  await page.evaluate(() => {
    const el = document.querySelector(".ai-summary-text, .ai-summary-pending, .next-action");
    if (el) el.scrollIntoView({ block: "center" });
  });
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(SHOT_DIR, "jobdetail-ai-summary.png") });
  console.log("shot jobdetail-ai-summary.png");
  await browser.close();
  console.log("done");
})().catch((err) => {
  console.error("SHOTS FAILED:", err);
  process.exit(1);
});
