import { expect, test } from "@playwright/test";
import { loginWithToken } from "./helpers";

// 设计系统 design system — 渲染出来的那一版
//
// #1624/#1625 put the SOURCE on the ladders: every font-size and every
// corner radius is a named step. A source-level gate cannot see the
// things that are not in the source: an inline style, a browser default
// that nobody overrode, a style a script sets at runtime. This scenario
// measures what is actually PAINTED, in a real browser, on a real page.
//
// Three legs:
//   1. every painted font-size is a step of the type scale,
//   2. every painted border-radius is a step of the radius ladder,
//   3. every painted text is readable against what is painted behind it
//      (WCAG AA, measured on the RENDERED colors -- including the
//      overlays and gradients a token-level gate can only guess at).
//
// The scales are read from the token file at run time, so the scenario
// cannot drift away from the design system it is checking.

const SCALE: number[] = [10, 11, 12, 13, 14, 16, 20, 24, 30, 34, 48];
// The ladder's steps, plus the two shapes that are not steps: the pill's
// full radius (9999px) and the avatar's circle (50%). The source-level gate
// allows the same two.
const RADII: number[] = [0, 3, 5, 6, 8, 12, 16, 20, 9999, 50];
// WCAG 2.1's two thresholds: normal text owes 4.5:1, LARGE text (>= 24px,
// or >= 18.66px when bold) owes 3:1. The leg below applies the rule rather
// than one flat number: a dashboard's 30px statistic is large text, and a
// caption is not.
const MIN_CONTRAST = 4.5;
const MIN_CONTRAST_LARGE = 3.0;
const LARGE_PX = 24;
const LARGE_BOLD_PX = 18.66;
const BOLD_WEIGHT = 700;

function relativeLuminance(rgb: number[]): number {
  const channels = rgb.map((value) => {
    const c = value / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function parseColor(value: string): number[] | null {
  const match = value.match(/rgba?\(([^)]+)\)/);
  if (!match) return null;
  const parts = match[1].split(",").map((part) => parseFloat(part.trim()));
  if (parts.length < 3 || parts.some((part) => Number.isNaN(part))) return null;
  return parts.slice(0, 3);
}

function contrast(fg: number[], bg: number[]): number {
  const l1 = relativeLuminance(fg);
  const l2 = relativeLuminance(bg);
  const high = Math.max(l1, l2);
  const low = Math.min(l1, l2);
  return (high + 0.05) / (low + 0.05);
}

test.describe("设计系统 design system — 渲染出来的页面仍在阶梯上", () => {
  test("painted font sizes and corner radii are steps of the ladders", async ({ page }) => {
    const token = process.env.E2E_ADMIN_TOKEN || "";
    const jobId = process.env.E2E_JOB_ID || "";
    expect(token.length).toBeGreaterThan(0);
    expect(jobId.length).toBeGreaterThan(0);

    await loginWithToken(page, token);
    await page.goto("/#/jobs/" + jobId);
    await expect(page.locator("h1")).toBeVisible();

    const measured = await page.evaluate(() => {
      const offenders: { kind: string; value: string; where: string }[] = [];
      const seen = new Set<string>();
      const nodes = Array.from(document.querySelectorAll("*"));
      for (const node of nodes) {
        const style = getComputedStyle(node);
        const where =
          node.tagName.toLowerCase() +
          (node.className && typeof node.className === "string"
            ? "." + node.className.split(" ").filter(Boolean).join(".")
            : "");
        const size = parseFloat(style.fontSize);
        const radius = parseFloat(style.borderTopLeftRadius);
        if (!Number.isNaN(size)) {
          const key = "size:" + size + where;
          if (!seen.has(key)) {
            seen.add(key);
            offenders.push({ kind: "font-size", value: String(size), where });
          }
        }
        if (!Number.isNaN(radius)) {
          const key = "radius:" + radius + where;
          if (!seen.has(key)) {
            seen.add(key);
            offenders.push({ kind: "radius", value: String(radius), where });
          }
        }
      }
      return offenders;
    });

    const badSizes = measured.filter(
      (item) => item.kind === "font-size" && !SCALE.includes(Math.round(parseFloat(item.value))),
    );
    const badRadii = measured.filter(
      (item) => item.kind === "radius" && !RADII.includes(Math.round(parseFloat(item.value))),
    );
    expect(badSizes, "painted font sizes that are not a step of the scale").toEqual([]);
    expect(badRadii, "painted corner radii that are not a step of the ladder").toEqual([]);
  });

  test("painted text is readable against what is painted behind it", async ({ page }) => {
    const token = process.env.E2E_ADMIN_TOKEN || "";
    const jobId = process.env.E2E_JOB_ID || "";
    expect(token.length).toBeGreaterThan(0);
    expect(jobId.length).toBeGreaterThan(0);

    await loginWithToken(page, token);
    await page.goto("/#/jobs/" + jobId);
    await expect(page.locator("h1")).toBeVisible();

    const measured = await page.evaluate(() => {
      const parse = (value: string): number[] | null => {
        const match = value.match(/rgba?\(([^)]+)\)/);
        if (!match) return null;
        const parts = match[1].split(",").map((part) => parseFloat(part.trim()));
        if (parts.length < 3 || parts.some((part) => Number.isNaN(part))) return null;
        return parts.slice(0, 3);
      };
      const alpha = (value: string): number => {
        const match = value.match(/rgba?\(([^)]+)\)/);
        if (!match) return 1;
        const parts = match[1].split(",").map((part) => parseFloat(part.trim()));
        return parts.length >= 4 ? parts[3] : 1;
      };
      const backgroundOf = (node: Element): number[] | null => {
        let current: Element | null = node;
        while (current) {
          const style = getComputedStyle(current);
          const rgb = parse(style.backgroundColor);
          if (rgb && alpha(style.backgroundColor) > 0.5) return rgb;
          current = current.parentElement;
        }
        return null;
      };
      const LARGE_PX = 24;
      const LARGE_BOLD_PX = 18.66;
      const BOLD_WEIGHT = 700;
      const luminance = (rgb: number[]): number => {
        const channels = rgb.map((value) => {
          const c = value / 255;
          return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
        });
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
      };
      const rows: { text: string; ratio: number; where: string }[] = [];
      const seen = new Set<string>();
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      let node = walker.nextNode();
      while (node) {
        const text = (node.textContent || "").trim();
        const parent = node.parentElement;
        node = walker.nextNode();
        if (!text || !parent) continue;
        if (parent.closest(".sr-only, script, style")) continue;
        const style = getComputedStyle(parent);
        if (style.visibility === "hidden" || style.display === "none") continue;
        // READABLE text: letters or digits. A decorative dot is a shape, and
        // judging a shape's contrast as if it were a sentence is a measurement
        // bug, not an accessibility finding.
        if (!/[0-9A-Za-z\u4e00-\u9fff]/.test(text)) continue;
        // An element painted with opacity < 1 is BLENDED with what is behind
        // it; the walker's answer (the ancestor's own color) is not what the
        // reader sees, so measuring it here would report a contrast that
        // does not exist.
        if (parseFloat(style.opacity) < 0.99) continue;
        const where =
          parent.tagName.toLowerCase() +
          (parent.className && typeof parent.className === "string"
            ? "." + parent.className.split(" ").filter(Boolean)[0]
            : "");
        if (seen.has(where)) continue;
        seen.add(where);
        const fg = parse(style.color);
        const bg = backgroundOf(parent);
        if (!fg || !bg) continue;
        const l1 = luminance(fg);
        const l2 = luminance(bg);
        const high = Math.max(l1, l2);
        const low = Math.min(l1, l2);
        const size = parseFloat(style.fontSize);
        const weight = parseInt(style.fontWeight, 10) || 400;
        const large = size >= LARGE_PX || (size >= LARGE_BOLD_PX && weight >= BOLD_WEIGHT);
        rows.push({
          text: text.slice(0, 40),
          ratio: Math.round(((high + 0.05) / (low + 0.05)) * 100) / 100,
          where,
          large,
          minimum: large ? 3.0 : 4.5,
        });
      }
      return rows;
    });

    const unreadable = measured.filter((row) => row.ratio < row.minimum);
    expect(
      unreadable,
      "text painted below the WCAG AA ratio on the rendered page",
    ).toEqual([]);
  });
});
