import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { loginWithToken } from "./helpers";

// The THEME baseline — what the product actually PAINTS, measured in a real
// browser, in both themes.
//
// WHY THIS IS NOT A SCREENSHOT. A pixel baseline is the usual way to catch
// "the design changed without anyone meaning it" — but pixels differ between
// a Windows dev box and a Linux CI runner (font rasterisation, shadows,
// gradients), so a pixel gate is either flaky or it has to be re-baselined
// per platform. The facts this file records are the ones that are NOT
// platform-dependent: the computed colours, radii, font sizes, spacing and
// shadows of a fixed set of surfaces. A theme-blind literal (the aurora
// layer's rgba() colours, #1640) shows up here as a colour that does NOT
// follow the theme — which is exactly the bug a screenshot would have
// caught too, but this one catches it on every platform.
//
// WHAT IS MEASURED. For each surface below, in each theme: the text
// colour, the painted background, the border colour, the radius, the font
// size and weight, the padding, the gap and the shadow. That is the
// "look" of the product in facts rather than in pixels.
//
// THE BASELINE IS A MEASUREMENT. It is committed, and a change to it is a
// change to the design — so the diff is printed and a reviewer decides.
// Run with UPDATE_THEME_BASELINE=1 to re-measure it (and commit the
// result): that is the same discipline as the fake inventory's re-pin.

const BASELINE = path.join(__dirname, "baselines", "theme-baseline.json");

// The surfaces the DASHBOARD actually paints (the class names are the
// page's own, read from its markup -- a selector that matches nothing
// would record a fact about nothing, and a baseline full of "__missing__"
// is a baseline that measures the wrong thing).
const SURFACES: [string, string][] = [
  ["body", "body"],
  ["shell", ".shell"],
  ["page", ".product-page"],
  ["panel", ".panel"],
  ["primary-button", ".btn.btn-primary"],
  ["quickstart-card", ".quickstart-card"],
  ["welcome-banner", ".welcome-banner"],
  ["eyebrow", ".eyebrow"],
  ["heading", ".product-page-heading h1"],
  ["brand-mark", ".brand-mark"],
];

const PROPERTIES = [
  "color",
  "backgroundColor",
  "borderTopColor",
  "borderRadius",
  "fontSize",
  "fontWeight",
  "paddingTop",
  "paddingLeft",
  "gap",
  "boxShadow",
] as const;

type Facts = Record<string, Record<string, string>>;

async function measure(page: import("@playwright/test").Page, theme: string): Promise<Facts> {
  await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
  // the theme change animates the colours; measuring mid-transition would
  // report a colour that exists for a few hundred milliseconds and nowhere
  // else (the design-system scenario makes the same point).
  await page.waitForTimeout(1200);
  return await page.evaluate(
    ({ surfaces, properties }) => {
      const out: Facts = {};
      for (const [name, selector] of surfaces) {
        const el = document.querySelector(selector);
        if (!el) {
          out[name] = { __missing__: "the selector matches nothing" };
          continue;
        }
        const style = getComputedStyle(el);
        const row: Record<string, string> = {};
        for (const property of properties) {
          row[property] = String(style[property as never] ?? "");
        }
        out[name] = row;
      }
      return out;
    },
    { surfaces: SURFACES, properties: PROPERTIES as unknown as string[] },
  );
}

function diff(expected: Facts, actual: Facts): string[] {
  const problems: string[] = [];
  for (const [name, row] of Object.entries(expected)) {
    const now = actual[name];
    if (!now) {
      problems.push(`${name}: the surface is gone`);
      continue;
    }
    for (const [property, value] of Object.entries(row)) {
      if (property.startsWith("__")) continue;
      const got = now[property];
      if (got !== value) {
        problems.push(`${name}.${property}: ${value} -> ${got}`);
      }
    }
  }
  for (const name of Object.keys(actual)) {
    if (!(name in expected)) problems.push(`${name}: a new surface appeared`);
  }
  return problems;
}

test.describe("主题基线 theme baseline", () => {
  test("the painted theme matches the committed baseline, in both themes", async ({ page }) => {
    const token = process.env.E2E_ADMIN_TOKEN || "";
    expect(token.length, "the theme baseline needs an admin token").toBeGreaterThan(0);
    await loginWithToken(page, token);
    await page.goto("/#/dashboard");
    await page.waitForTimeout(800);
    // Animation and transition OFF, before the theme is switched. The brand
    // mark's glow is a breathing animation, so its computed shadow is a
    // different number every millisecond -- a baseline would record a
    // snapshot of an animation, and the next run would call it a change.
    // What this file measures is the THEME, and the theme is what the
    // animation starts from.
    await page.addStyleTag({
      content:
        "*, *::before, *::after { animation: none !important; transition: none !important; }",
    });

    const measured: Record<string, Facts> = {};
    for (const theme of ["light", "dark"]) {
      measured[theme] = await measure(page, theme);
    }

    if (process.env.UPDATE_THEME_BASELINE === "1") {
      mkdirSync(path.dirname(BASELINE), { recursive: true });
      writeFileSync(BASELINE, JSON.stringify(measured, null, 2) + "\n", "utf8");
      test.info().annotations.push({ type: "baseline", description: "re-measured" });
      return;
    }

    expect(
      existsSync(BASELINE),
      "the theme baseline is missing — measure it once with UPDATE_THEME_BASELINE=1 and commit it",
    ).toBe(true);
    const expected = JSON.parse(readFileSync(BASELINE, "utf8")) as Record<string, Facts>;
    const problems: string[] = [];
    for (const theme of ["light", "dark"]) {
      problems.push(...diff(expected[theme] ?? {}, measured[theme]));
    }
    expect(
      problems,
      "the painted theme moved. If the change is intended, re-measure with "
        + "UPDATE_THEME_BASELINE=1 and commit the new baseline; if it is not, "
        + "this is the regression.",
    ).toEqual([]);
  });
});
