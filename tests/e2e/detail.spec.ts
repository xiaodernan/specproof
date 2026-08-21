import { expect, test } from "@playwright/test";
import { loginWithToken } from "./helpers";

// 详情 scenario: the verification-job detail page renders the matrix
// summary, the report/artifact section, the stage timeline, findings and
// the certificate — plus the requirement-matrix rows on the Matrix page.
test.describe("详情 detail — 任务详情渲染矩阵/报告区块", () => {
  test("job detail renders matrix stats, report, stages, findings, certificate", async ({
    page,
  }) => {
    const token = process.env.E2E_ADMIN_TOKEN || "";
    const jobId = process.env.E2E_JOB_ID || "";
    expect(token.length).toBeGreaterThan(0);
    expect(jobId.length).toBeGreaterThan(0);

    await loginWithToken(page, token);
    await page.goto("/#/jobs");
    await page.locator("tbody tr", { hasText: "e2e/demo-repo" }).first().click();
    await expect(page).toHaveURL(new RegExp("#/jobs/" + jobId));

    // Overview tab: matrix summary stat cards + report artifact section.
    await expect(page.getByText("判定 Verdict")).toBeVisible();
    await expect(page.getByText("VERIFIED", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("合约 Contracts")).toBeVisible();
    await expect(page.getByText("PASS", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("FAIL", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("证据与产物 Artifacts")).toBeVisible();
    await expect(page.getByText("reports/verify-e2e00000.html")).toBeVisible();

    // Stages tab: seeded pipeline timeline.
    await page.getByText("阶段 Stages").click();
    await expect(page.getByText("intake")).toBeVisible();
    await expect(page.getByText("compile_contracts")).toBeVisible();
    await expect(page.getByText("publish_report")).toBeVisible();

    // Findings tab: the seeded MAJOR finding on contract AUTH-02.
    await page.getByText(/Findings \(1\)/).click();
    await expect(page.getByText("AUTH-02")).toBeVisible();
    await expect(page.getByText("MAJOR")).toBeVisible();

    // Certificate tab: fixture-persisted merge certificate document.
    await page.getByText("证书 Certificate").click();
    await expect(page.getByText("合并证书 / 拒绝通知")).toBeVisible();
    await expect(page.getByText(/"verdict": "VERIFIED"/)).toBeVisible();

    // Matrix page: requirement-to-evidence rows for the same job.
    await page.goto("/#/matrix");
    await page.locator("select").selectOption(jobId);
    await expect(page.getByText("AUTH-01")).toBeVisible();
    await expect(page.getByText("AUTH-02")).toBeVisible();
    await expect(page.locator(".pill", { hasText: "PASS" })).toBeVisible();
    await expect(page.locator(".pill", { hasText: "FAIL" })).toBeVisible();
  });
});
