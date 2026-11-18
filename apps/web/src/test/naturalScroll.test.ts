/**
 * Natural-scroll guard — the owner's repeated complaint was that the wheel
 * was inverted at some point in the past; the only global scroll listener in
 * the product is CoachMarks' passive:true capture listener (dwell-time
 * measurement; it does not preventDefault or invert the direction). Any future
 * scroll-jacking or inversion in product source must fail this test before it
 * reaches a visitor.
 *
 * Rule: product source SHALL NOT cancel or invert wheel semantics. The one
 * legitimate dwell-time listener is whitelisted.
 */
import { describe, expect, it } from "vitest";

const modules = import.meta.glob<string>(["../**/*.tsx", "../**/*.ts", "../**/*.js"], {
  query: "?raw",
  import: "default",
  eager: true,
});

const ALLOWED = new Set<string>([
  "../ui/CoachMarks.tsx",
]);

describe("scroll direction stays natural", () => {
  it("no product code cancels or inverts wheel/scroll", () => {
    const offenders: string[] = [];
    for (const [file, source] of Object.entries(modules)) {
      if (ALLOWED.has(file)) continue;
      if (/\.test\.|\.spec\.|__tests__/.test(file)) continue;
      const src = source.replace(/\/\*[\s\S]*?\*\//g, "");
      const lines = src.split("\n");
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const stripped = line.replace(/\/\/.*/, "");
        if (/WheelEvent|onWheel|wheel\.(preventDefault|stopPropagation|stopImmediatePropagation)|addEventListener\s*\(\s*['"]wheel/.test(
          stripped,
        )) {
          offenders.push(`${file}:${i + 1}: ${line.trim()}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
