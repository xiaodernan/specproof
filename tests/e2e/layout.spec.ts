import { expect, test } from "@playwright/test";

/**
 * The LAYOUT of the real app, measured in a real browser.
 *
 * The design-system scenario measures COLOURS and SIZES (tokens, contrast,
 * the type ladder). It cannot see LAYOUT — and layout is what a reader
 * notices first: text clipped by its own box, a control too small to hit,
 * a page that scrolls sideways on a phone.
 *
 * <p>Three defects, three measurable shapes:</p>
 * <ul>
 *   <li><b>overflow</b>: the document is wider than the viewport — a
 *       horizontal scrollbar on a phone is the classic "this site was
 *       designed on a desktop" tell;</li>
 *   <li><b>clipped</b>: a text box whose own content is wider than it, with
 *       the overflow hidden and no ellipsis — a sentence cut in half with
 *       no way to read the rest;</li>
 *   <li><b>tiny</b>: a control smaller than 24×24 — a button you cannot hit
 *       with a finger. (An inline text link is not a control: a 19px tall
 *       link is typography, not a tap target.)</li>
 * </ul>
 *
 * <p>Coverage: every product page × both themes × a desktop and a phone
 * viewport. The theme is the real one — the app follows
 * {@code prefers-color-scheme} — so the dark theme is measured as the dark
 * theme, not as a class somebody toggled.</p>
 */
const PAGES = [
  ["dashboard", "/#/"],
  ["jobs", "/#/jobs"],
  ["job-detail", "/#/jobs/demo-1"],
  ["identity", "/#/identity"],
] as const;

const VIEWPORTS = [
  ["desktop", { width: 1440, height: 900 }],
  ["phone", { width: 390, height: 844 }],
] as const;

type Layout = {
  overflowX: number;
  clipped: { el: string; text: string; scrollWidth: number; clientWidth: number }[];
  tiny: { el: string; w: number; h: number; text: string }[];
};

async function measure(page: import("@playwright/test").Page): Promise<Layout> {
  return page.evaluate(() => {
    const out = {
      overflowX: 0,
      clipped: [] as { el: string; text: string; scrollWidth: number; clientWidth: number }[],
      tiny: [] as { el: string; w: number; h: number; text: string }[],
    };
    out.overflowX =
      document.documentElement.scrollWidth - document.documentElement.clientWidth;
    const describe = (el: Element): string => {
      const id = el.id ? "#" + el.id : "";
      const cls =
        typeof el.className === "string" && el.className.trim()
          ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".")
          : "";
      return el.tagName.toLowerCase() + id + cls;
    };
    for (const el of Array.from(document.querySelectorAll("*"))) {
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") continue;
      if (
        el.children.length === 0 &&
        el.textContent &&
        el.textContent.trim().length > 0 &&
        el.scrollWidth > el.clientWidth + 2 &&
        style.overflowX === "hidden" &&
        style.textOverflow !== "ellipsis"
      ) {
        out.clipped.push({
          el: describe(el),
          text: el.textContent.trim().slice(0, 60),
          scrollWidth: el.scrollWidth,
          clientWidth: el.clientWidth,
        });
      }
      const isButton =
        el.tagName === "BUTTON" || ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName);
      const isIconLink = el.tagName === "A" && !(el.textContent || "").trim();
      if (isButton || isIconLink) {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) continue;
        if (rect.width < 24 || rect.height < 24) {
          out.tiny.push({
            el: describe(el),
            w: Math.round(rect.width),
            h: Math.round(rect.height),
            text: (el.textContent || el.getAttribute("aria-label") || "").trim().slice(0, 40),
          });
        }
      }
    }
    out.clipped = out.clipped.slice(0, 12);
    out.tiny = out.tiny.slice(0, 12);
    return out;
  });
}

for (const [viewportName, viewport] of VIEWPORTS) {
  for (const theme of ["light", "dark"] as const) {
    test(`layout holds on every page (${viewportName}, ${theme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme });
      const problems: string[] = [];
      for (const [pageName, path] of PAGES) {
        await page.setViewportSize(viewport);
        await page.goto(path);
        await page.waitForTimeout(800);
        const layout = await measure(page);
        if (layout.overflowX > 1) {
          problems.push(
            `${pageName}: the document is ${layout.overflowX}px wider than the viewport`
          );
        }
        for (const clipped of layout.clipped) {
          problems.push(
            `${pageName}: clipped text in ${clipped.el} "${clipped.text}" ` +
              `(${clipped.scrollWidth}px of text in ${clipped.clientWidth}px)`
          );
        }
        for (const tiny of layout.tiny) {
          problems.push(
            `${pageName}: control ${tiny.el} is ${tiny.w}x${tiny.h} "${tiny.text}"`
          );
        }
      }
      expect(problems, problems.join("\n")).toEqual([]);
    });
  }
}
