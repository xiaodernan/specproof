import { expect, test } from "@playwright/test";
import { loginWithToken } from "./helpers";

// 长理由 long text (#122), measured in a real browser.
//
// The claim under test is NOT "a long reason used to widen the page". Measured
// 2026-09-29 in this browser: a panel-hosted table never widened this page --
// `.panel { overflow: hidden }` (styles/base.css:1369) clips instead, and the
// shell's own scroller is `.content` (base.css:1363), not the document. So the
// damage has the same shape and is worse to live with: the reason is cut off
// with no scrollbar that could reach the rest of it.
//
// That makes the property worth measuring "is the overflowing text reachable?",
// and it makes a control arm mandatory: the same 300 characters, in the markup
// this page used to render, appended to the same panel-body. Without the
// control, a green real arm could just be an assertion about nothing.
test.describe("长理由 long text — 一处不换行的理由必须够得到 (#122)", () => {
  test("the reviewer ledger keeps a 300-char reason scrollable, not clipped", async ({ page }) => {
    const token = process.env.E2E_ADMIN_TOKEN || "";
    const jobId = process.env.E2E_JOB_ID || "";
    expect(token.length).toBeGreaterThan(0);
    expect(jobId.length).toBeGreaterThan(0);

    await loginWithToken(page, token);
    // The SPA's finding route is #/findings/<jobId>/<findingId> (App.tsx), not a
    // tab under the job.
    await page.goto("/#/findings/" + jobId + "/f-1");
    const reasonCell = page.locator(".ui-table td", { hasText: "证据不足" });
    await expect(reasonCell.first()).toBeVisible();

    const measured = await page.evaluate((needle: string) => {
      // The first ancestor that clips decides whether overflowing content is
      // reachable: `auto`/`scroll` hands the reader a scrollbar, `hidden`/`clip`
      // throws the rest of the string away. Walking the real computed styles is
      // the point -- a class-name assertion cannot tell the two apart.
      const clipper = (start: Element | null) => {
        let node: Element | null = start?.parentElement ?? null;
        while (node) {
          const overflowX = getComputedStyle(node).overflowX;
          if (overflowX !== "visible") {
            const el = node as HTMLElement;
            return {
              className: String(node.className),
              overflowX,
              clientWidth: el.clientWidth,
              scrollWidth: el.scrollWidth,
            };
          }
          node = node.parentElement;
        }
        return null;
      };

      const cell = Array.from(document.querySelectorAll(".ui-table td")).find((el) =>
        (el.textContent || "").includes(needle),
      ) as HTMLElement | undefined;
      if (!cell) return null;
      const text = cell.textContent || "";
      const real = { text, clipper: clipper(cell), cellWidth: cell.getBoundingClientRect().width };

      // Control arm: the same characters, through the markup this page used to
      // render, in the same panel-body. Removed again so the real page is what
      // the rest of the suite sees.
      const host = cell.closest(".panel-body") as HTMLElement;
      const table = document.createElement("table");
      table.className = "data";
      const tbody = document.createElement("tbody");
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.textContent = text;
      tr.appendChild(td);
      tbody.appendChild(tr);
      table.appendChild(tbody);
      host.appendChild(table);
      const control = {
        clipper: clipper(td),
        tableWidth: table.getBoundingClientRect().width,
      };
      table.remove();

      const content = document.querySelector(".content") as HTMLElement | null;
      return {
        real,
        control,
        page: content
          ? { clientWidth: content.clientWidth, scrollWidth: content.scrollWidth }
          : null,
      };
    }, "证据不足");

    expect(measured, "the reviewer ledger row never rendered: 证据不足 not found").not.toBeNull();
    const { real, control, page: content } = measured!;

    // Real arm: the shared wrapper is the nearest clipper, it scrolls, and the
    // long run really does overflow it -- i.e. the scrollbar is doing work.
    expect(real.text.length, "the fixture's long reason: " + JSON.stringify(real)).toBeGreaterThan(300);
    expect(real.clipper?.className, "nearest clipper of the reason cell").toContain("ui-table-wrap");
    expect(real.clipper?.overflowX, "wrapper must scroll, not clip: " + JSON.stringify(real)).toBe("auto");
    expect(
      real.clipper!.scrollWidth,
      "the long value must overflow the wrapper, or this proves nothing: " + JSON.stringify(real),
    ).toBeGreaterThan(real.clipper!.clientWidth);

    // The page itself stays put: the ledger's overflow is absorbed inside the
    // panel instead of growing the shell's scroller.
    expect(
      content!.scrollWidth,
      "the ledger must not widen the content area: " + JSON.stringify(measured),
    ).toBeLessThanOrEqual(content!.clientWidth + 1);

    // Control arm: identical string, identical browser, identical CSS -- only
    // the markup differs, and there the text is clipped with nothing to scroll.
    expect(
      control.clipper?.className ?? "",
      "the old markup's overflow must not land in a scroll container: " + JSON.stringify(control),
    ).not.toContain("ui-table-wrap");
    expect(
      control.tableWidth,
      "the control must actually overflow what holds it: " + JSON.stringify(control),
    ).toBeGreaterThan(control.clipper!.clientWidth);
    expect(
      control.clipper?.overflowX,
      "the old markup was clipped, not scrollable: " + JSON.stringify(control),
    ).toBe("hidden");
  });
});
