import { chromium } from "@playwright/test";
import fs from "fs";

const STATE = JSON.parse(
  fs.readFileSync("D:\\面试项目\\specproof-reference\\tests\\e2e\\.state\\e2e-state.json", "utf8"),
);
const SHOT_DIR = "D:\\面试项目\\shots";
fs.mkdirSync(SHOT_DIR, { recursive: true });

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });

  await page.goto("http://127.0.0.1:5174/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "访问令牌", exact: true }).click();
  await page.locator("#credential").fill(STATE.admin_token);
  await page.getByRole("button", { name: "连接工作区", exact: true }).click();
  await page.locator(".shell").waitFor({ state: "visible", timeout: 30_000 });

  await page.goto("http://127.0.0.1:5174/#/jobs/" + encodeURIComponent(STATE.job_id), {
    waitUntil: "domcontentloaded",
  });
  await page.waitForTimeout(2500);

  const stagesTab = page.getByRole("tab", { name: "执行进度", exact: true });
  await stagesTab.click();
  await page.waitForTimeout(1200);

  const panel = page.locator(".panel", { hasText: "执行阶段" }).first();
  await panel.scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);
  await panel.screenshot({ path: SHOT_DIR + "\\jobdetail-stages-timeline.png" });
  console.log("shot jobdetail-stages-timeline.png");

  const hasTimeline = (await page.locator(".stage-timeline").count()) > 0;
  console.log("stage-timeline present:", hasTimeline);
  if (hasTimeline) {
    const bars = await page.locator(".stage-timeline-bar").count();
    const labels = await page.locator(".stage-timeline-row").allInnerTexts();
    console.log("bars:", bars, "labels:", JSON.stringify(labels));
  }
  await browser.close();
  console.log("done");
})().catch((err) => {
  console.error("SHOTS FAILED:", err);
  process.exit(1);
});
