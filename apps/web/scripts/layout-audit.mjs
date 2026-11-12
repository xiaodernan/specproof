/**
 * A layout audit of the real app in a real browser.
 *
 * The design-system gate measures COLOURS and SIZES (tokens, contrast, the
 * type ladder). It cannot see LAYOUT: a card whose content is clipped, a
 * button too small to hit, a page that scrolls sideways on a phone. Those
 * are the defects a reader actually notices, and they are measurable in the
 * browser — so this measures them.
 *
 * Run from apps/web (the playwright package lives in its node_modules):
 *   node scripts/layout-audit.mjs
 */
import { chromium } from "playwright";

const BASE = process.env.SPECPROOF_E2E_BASE || "http://127.0.0.1:5174";
const PAGES = [
  ["dashboard", "/#/"],
  ["jobs", "/#/jobs"],
  ["job-detail", "/#/jobs/demo-1"],
  ["identity", "/#/identity"],
];
const THEMES = ["light", "dark"];
const VIEWPORTS = [
  ["desktop", { width: 1440, height: 900 }],
  ["phone", { width: 390, height: 844 }],
];

const PROBE = `() => {
  const out = { overflowX: 0, clipped: [], tiny: [], docWidth: 0, viewWidth: 0 };
  out.docWidth = document.documentElement.scrollWidth;
  out.viewWidth = document.documentElement.clientWidth;
  out.overflowX = out.docWidth - out.viewWidth;
  const describe = (el) => {
    const id = el.id ? "#" + el.id : "";
    const cls = (el.className && typeof el.className === "string")
      ? "." + el.className.trim().split(/\\s+/).slice(0, 2).join(".")
      : "";
    return el.tagName.toLowerCase() + id + cls;
  };
  for (const el of document.querySelectorAll("*")) {
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    // a text container that clips its own text without offering a scrollbar
    if (
      el.children.length === 0 &&
      el.textContent && el.textContent.trim().length > 0 &&
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
    // a control too small to hit. An inline text link is NOT a control: its
    // line box is the text, and 19px tall links are normal typography. A
    // BUTTON (or a link with no text of its own — an icon link) is.
    const isButton = el.tagName === "BUTTON"
      || ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName);
    const isIconLink = el.tagName === "A" && !(el.textContent || "").trim();
    if (isButton || isIconLink) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      if (r.width < 24 || r.height < 24) {
        out.tiny.push({
          el: describe(el),
          w: Math.round(r.width),
          h: Math.round(r.height),
          text: (el.textContent || el.getAttribute("aria-label") || "").trim().slice(0, 40),
        });
      }
    }
  }
  out.clipped = out.clipped.slice(0, 12);
  out.tiny = out.tiny.slice(0, 12);
  return out;
}`;

const browser = await chromium.launch();
const report = [];
for (const [vpName, viewport] of VIEWPORTS) {
  for (const theme of THEMES) {
    for (const [name, path] of PAGES) {
      const page = await browser.newPage({ viewport });
      await page.emulateMedia({ colorScheme: theme });
      await page.goto(BASE + path, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(1200);
      const probe = await page.evaluate(new Function("return " + PROBE)());
      report.push({ viewport: vpName, theme, page: name, ...probe });
      await page.close();
    }
  }
}
await browser.close();

let defects = 0;
for (const row of report) {
  const bad = row.overflowX > 1 || row.clipped.length > 0 || row.tiny.length > 0;
  if (bad) defects += 1;
  console.log(
    `${bad ? "DEFECT" : "  ok  "} ${row.viewport.padEnd(7)} ${row.theme.padEnd(5)} ${row.page.padEnd(11)}` +
    ` overflowX=${row.overflowX} clipped=${row.clipped.length} tiny=${row.tiny.length}`
  );
  for (const c of row.clipped) console.log(`        clipped: ${c.el} "${c.text}" ${c.scrollWidth}>${c.clientWidth}`);
  for (const t of row.tiny) console.log(`        tiny:    ${t.el} ${t.w}x${t.h} "${t.text}"`);
}
console.log(`\n${defects} of ${report.length} page/theme/viewport combinations carry a layout defect`);
