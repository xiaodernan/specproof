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
//
// The second scenario measures the one site #122 did NOT migrate,
// pages/Dashboard.tsx's recent-jobs table, whose entry in the table register
// rests on a source-level claim: it is wrapped in its own `.table-scroll` box
// AND its grid track is `minmax(0, 2.1fr)`. The `minmax(0, ...)` half is the one
// worth putting in front of a layout engine -- with a plain `2.1fr` track, the
// track's min-content width comes from the widest cell, so the page grows
// sideways and the inner scroll box has nothing left to absorb. That is measured
// here by mutating the track in the browser and reading the same boxes again.
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

  test("the dashboard's own scroll box absorbs a long repo name, and minmax(0, …) is why", async ({ page }) => {
    const token = process.env.E2E_ADMIN_TOKEN || "";
    expect(token.length).toBeGreaterThan(0);
    await loginWithToken(page, token);
    await page.goto("/#/dashboard");
    await expect(page.locator(".table-scroll table.data tbody tr").first()).toBeVisible();

    const measured = await page.evaluate((run: string) => {
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
      const box = (selector: string) => {
        const el = document.querySelector(selector) as HTMLElement | null;
        return el ? { clientWidth: el.clientWidth, scrollWidth: el.scrollWidth } : null;
      };

      // The fixture's demo job has a short name, so the long value is injected
      // into a CLONE of the page's own row: same elements, same classes, same
      // CSS path -- only the text differs, which is the only thing a real
      // repository could also make long.
      const tbody = document.querySelector(".table-scroll table.data tbody") as HTMLElement;
      const row = tbody.querySelector("tr")!.cloneNode(true) as HTMLElement;
      const title = row.querySelector(".job-title") as HTMLElement;
      title.textContent = run;
      tbody.appendChild(row);
      const cell = title.parentElement as HTMLElement;

      const shipped = {
        runLength: run.length,
        clipper: clipper(cell),
        content: box(".content"),
        dashboardBottom: box(".dashboard-bottom"),
      };

      // Counterfactual: the same 300 characters, the same DOM, one CSS
      // declaration weaker -- a grid track that is no longer allowed to shrink
      // below its min-content width.
      const bottom = document.querySelector(".dashboard-bottom") as HTMLElement;
      bottom.style.gridTemplateColumns = "2.1fr minmax(250px, 1fr)";
      const naive = {
        clipper: clipper(cell),
        content: box(".content"),
        dashboardBottom: box(".dashboard-bottom"),
      };
      bottom.style.gridTemplateColumns = "";
      row.remove();
      return { shipped, naive };
    }, "r".repeat(300));

    const { shipped, naive } = measured;
    expect(shipped.runLength).toBe(300);

    // Shipped: the inner box is the nearest clipper and it really scrolls, so the
    // rest of the name is reachable. The page itself does not grow.
    expect(shipped.clipper?.className, "nearest clipper: " + JSON.stringify(shipped)).toContain("table-scroll");
    expect(shipped.clipper?.overflowX, "the box must scroll: " + JSON.stringify(shipped)).toBe("auto");
    expect(
      shipped.clipper!.scrollWidth,
      "the long name must overflow the box, or this proves nothing: " + JSON.stringify(shipped),
    ).toBeGreaterThan(shipped.clipper!.clientWidth);
    expect(
      shipped.content!.scrollWidth,
      "the dashboard must not widen .content: " + JSON.stringify(shipped),
    ).toBeLessThanOrEqual(shipped.content!.clientWidth + 1);

    // Naive track: the property is gone -- the page is wider than its viewport
    // and the inner box has nothing left to absorb, which is exactly the failure
    // mode the `minmax(0, ...)` in .dashboard-bottom prevents.
    expect(
      naive.clipper!.scrollWidth,
      "with a plain 2.1fr track the inner box should stop absorbing: " + JSON.stringify(naive),
    ).toBeLessThanOrEqual(naive.clipper!.clientWidth + 1);
    expect(
      naive.content!.scrollWidth,
      "with a plain 2.1fr track the page should widen instead: " + JSON.stringify(naive),
    ).toBeGreaterThan(naive.content!.clientWidth);
  });
});
