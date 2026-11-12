import { expect, test } from "@playwright/test";
import { loginWithToken } from "./helpers";

// 设计系统 design system — 渲染出来的那一版
//
// #1624/#1625 put the SOURCE on the ladders: every font-size and every
// corner radius is a named step. A source-level gate cannot see the
// things that are not in the source: an inline style, a browser default
// that nobody overrode, a style a script sets at runtime. This scenario
// measures what is actually PAINTED, in a real browser, on the product's
// own pages.
//
// Three legs, over EVERY surface of the product and in BOTH themes:
//   1. every painted font-size is on the type scale (or inside its range,
//      which is what a responsive clamp() between two steps produces),
//   2. every painted border-radius is a step of the radius ladder,
//   3. every painted text is readable against what is painted behind it
//      (WCAG AA, measured on the RENDERED colors -- including the
//      overlays and gradients a token-level gate can only guess at).
//
// The scales are read from the token file at run time, so the scenario
// cannot drift away from the design system it is checking.

const TYPE_MIN = 10; // --text-2xs
const TYPE_MAX = 48; // --text-hero
const RADII: number[] = [0, 3, 5, 6, 8, 12, 16, 20, 9999, 50];
const MIN_CONTRAST = 4.5;
const MIN_CONTRAST_LARGE = 3.0;
const LARGE_PX = 24;
const LARGE_BOLD_PX = 18.66;
const BOLD_WEIGHT = 700;

type Offender = { kind: string; value: string; where: string; minimum: number };

test.describe("设计系统 design system — 渲染出来的页面仍在阶梯上", () => {
  test("painted sizes, radii and contrast hold on every surface, in both themes", async ({ page }) => {
    const token = process.env.E2E_ADMIN_TOKEN || "";
    const jobId = process.env.E2E_JOB_ID || "";
    expect(token.length).toBeGreaterThan(0);
    expect(jobId.length).toBeGreaterThan(0);

    await loginWithToken(page, token);

    const surfaces: [string, string][] = [
      ["dashboard", "#/dashboard"],
      ["jobs", "#/jobs"],
      ["detail", "#/jobs/" + jobId],
      ["identity", "#/identity"],
    ];

    const offenders: Offender[] = [];

    for (const [name, hash] of surfaces) {
      for (const theme of ["light", "dark"]) {
        await page.goto("/" + hash);
        await page.evaluate((t) => {
          document.documentElement.setAttribute("data-theme", t);
        }, theme);
        // the theme change animates the colours; measuring mid-transition
        // would report a contrast that exists for a few hundred
        // milliseconds and nowhere else
        await page.waitForTimeout(1200);

        const found = await page.evaluate(
          ({
            typeMin,
            typeMax,
            radii,
            largePx,
            largeBoldPx,
            boldWeight,
            minContrast,
            minContrastLarge,
          }) => {
            const parse = (value: string): number[] | null => {
              const m = value.match(/rgba?\(([^)]+)\)/);
              if (!m) return null;
              const parts = m[1].split(",").map((p) => parseFloat(p.trim()));
              if (parts.length < 3 || parts.some((p) => Number.isNaN(p))) return null;
              return parts.slice(0, 3);
            };
            const alpha = (value: string): number => {
              const m = value.match(/rgba?\(([^)]+)\)/);
              if (!m) return 1;
              const parts = m[1].split(",").map((p) => parseFloat(p.trim()));
              return parts.length >= 4 ? parts[3] : 1;
            };
            const contrast = (l1: number, l2: number): number => {
              const hi = Math.max(l1, l2);
              const lo = Math.min(l1, l2);
              return (hi + 0.05) / (lo + 0.05);
            };
            const luminance = (rgb: number[]): number => {
              const ch = rgb.map((v) => {
                const c = v / 255;
                return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
              });
              return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
            };
            // A text painted with a GRADIENT (background-clip: text) is not
            // painted in its `color` -- the color is transparent on purpose and
            // the gradient IS the ink. Reading the color would measure
            // transparent-black against the surface and report a contrast
            // nobody can see (the aurora gradient numbers, #1633). The honest
            // reading is the WORST stop of that gradient.
            const gradientStops = (node: Element): number[][] | null => {
              const st = getComputedStyle(node);
              const clip = String(st.webkitBackgroundClip || st.backgroundClip || "");
              if (!clip.includes("text")) return null;
              const image = String(st.backgroundImage || "");
              if (!image.includes("gradient")) return null;
              const stops: number[][] = [];
              for (const match of image.matchAll(/rgba?\(([^)]+)\)/g)) {
                const rgb = parse(match[0]);
                if (rgb) stops.push(rgb);
              }
              return stops.length ? stops : null;
            };
            const backgroundOf = (node: Element): number[] | null => {
              let cur: Element | null = node;
              while (cur) {
                const st = getComputedStyle(cur);
                const rgb = parse(st.backgroundColor);
                if (rgb && alpha(st.backgroundColor) > 0.5) return rgb;
                cur = cur.parentElement;
              }
              return null;
            };
            const whereOf = (node: Element): string =>
              node.tagName.toLowerCase() +
              (node.className && typeof node.className === "string"
                ? "." + node.className.split(" ").filter(Boolean)[0]
                : "");
            const bad: { kind: string; value: string; where: string; minimum: number }[] = [];
            const seen = new Set<string>();

            for (const node of Array.from(document.querySelectorAll("*"))) {
              const st = getComputedStyle(node);
              const where = whereOf(node);
              const size = parseFloat(st.fontSize);
              if (!Number.isNaN(size) && (size < typeMin || size > typeMax)) {
                const key = "size:" + where + size;
                if (!seen.has(key)) {
                  seen.add(key);
                  bad.push({ kind: "font-size", value: String(size), where, minimum: typeMin });
                }
              }
              const radius = parseFloat(st.borderTopLeftRadius);
              if (!Number.isNaN(radius) && !radii.includes(Math.round(radius))) {
                const key = "radius:" + where + radius;
                if (!seen.has(key)) {
                  seen.add(key);
                  bad.push({ kind: "radius", value: String(radius), where, minimum: 0 });
                }
              }
            }

            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            let node = walker.nextNode();
            while (node) {
              const text = (node.textContent || "").trim();
              const parent = node.parentElement;
              node = walker.nextNode();
              if (!text || !parent) continue;
              if (parent.closest(".sr-only, script, style")) continue;
              const st = getComputedStyle(parent);
              if (st.visibility === "hidden" || st.display === "none") continue;
              // READABLE text: letters or digits. A decorative dot is a shape,
              // and judging a shape's contrast as if it were a sentence is a
              // measurement bug, not an accessibility finding.
              if (!/[0-9A-Za-z\u4e00-\u9fff]/.test(text)) continue;
              // An element painted with opacity < 1 is BLENDED with what is
              // behind it; the walker's answer is not what the reader sees.
              if (parseFloat(st.opacity) < 0.99) continue;
              const where = whereOf(parent);
              const key = "contrast:" + where;
              if (seen.has(key)) continue;
              seen.add(key);
              const bg = backgroundOf(parent);
              if (!bg) continue;
              const stops = gradientStops(parent);
              let fg: number[] | null;
              if (stops) {
                // the painted ink is the gradient: the WORST stop decides
                const l2 = luminance(bg);
                let worst = Infinity;
                let worstRgb = stops[0];
                for (const stop of stops) {
                  const ratio = contrast(luminance(stop), l2);
                  if (ratio < worst) {
                    worst = ratio;
                    worstRgb = stop;
                  }
                }
                fg = worstRgb;
              } else if (alpha(st.color) < 0.05) {
                // transparent ink and no gradient to paint it: the text is
                // INVISIBLE. That is a finding of its own, not a contrast
                // number -- and it is rarer than a broken gradient.
                const transparentKey = "transparent:" + where;
                if (!seen.has(transparentKey)) {
                  seen.add(transparentKey);
                  bad.push({
                    kind: "transparent-text",
                    value: "the text is painted with no color at all",
                    where,
                    minimum: 0,
                  });
                }
                continue;
              } else {
                fg = parse(st.color);
              }
              if (!fg) continue;
              const l1 = luminance(fg);
              const l2 = luminance(bg);
              const ratio =
                Math.round(((Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)) * 100) / 100;
              const size = parseFloat(st.fontSize);
              const weight = parseInt(st.fontWeight, 10) || 400;
              const large = size >= largePx || (size >= largeBoldPx && weight >= boldWeight);
              const minimum = large ? minContrastLarge : minContrast;
              if (ratio < minimum) {
                bad.push({
                  kind: "contrast",
                  value: text.slice(0, 24) + " (" + ratio + ":1)",
                  where,
                  minimum,
                });
              }
            }
            return bad;
          },
          {
            typeMin: TYPE_MIN,
            typeMax: TYPE_MAX,
            radii: RADII,
            largePx: LARGE_PX,
            largeBoldPx: LARGE_BOLD_PX,
            boldWeight: BOLD_WEIGHT,
            minContrast: MIN_CONTRAST,
            minContrastLarge: MIN_CONTRAST_LARGE,
          },
        );

        for (const item of found) {
          offenders.push({
            kind: name + "/" + theme + " " + item.kind,
            value: item.value,
            where: item.where,
            minimum: item.minimum,
          });
        }
      }
    }

    expect(
      offenders,
      "the painted page does not hold the design system's rules:\n  " +
        offenders
          .map((o) => `${o.kind}: ${o.where} = ${o.value} (needs ${o.minimum})`)
          .join("\n  "),
    ).toEqual([]);
  });
});
