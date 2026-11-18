/**
 * wheel/natural-scroll guard — the owner's repeated complaint was that the wheel
 * was inverted at some point in the past; the one and only global scroll listener
 * in the product is the `CoachMarks` passive:true capture listener used to
 * observe dwell time for onboarding. Any future scroll-jacking must go red here
 * before it ships.
 *
 * Rule: no wheel event SHALL ever be handled, inverted, cancelled or mutated
 * in product source. If you find a legitimate need to scroll programomatically,
 * use scrollTo(..., { behavior: "smooth" }) only — never touch deltaY sign.
 * (Excludes node_modules / dist by construction.)
 */
import { describe, expect, it } from "vitest";
import { fileURLToPath } from "node:url";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const SRC = join(
  fileURLToPath(import.meta.url),
  "..",
  "..",
); // apps/web/src

function* files(dir: string): Iterable<string> {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) yield* files(full);
    else if (/\.(ts|tsx|js|jsx)$/.test(name) && !/\.test\.|__tests__/.test(name)) yield full;
  }
}

const ALLOWED = new Set<string>([
  join(SRC, "ui", "CoachMarks.tsx"),
]);

describe("scroll direction stays natural", () => {
  it("no product code cancels or inverts wheel/scroll", () => {
    const offenders: string[] = [];
    for (const file of files(SRC)) {
      if (ALLOWED.has(file)) continue;
      const src = readFileSync(file, "utf8");
      // strip block comments then line comments
      const noBlock = src.replace(/\/\*[\s\S]*?\*\//g, "");
      const lines = noBlock.split("\n");
      for (let i = 0; i < lines.length; i++) {
        const stripped = lines[i].replace(/\/\/.*/, "");
        if (/WheelEvent|onWheel|wheel.*addEventListener|wheel.*dispatchEvent/.test(stripped)) {
          const rel = relative(SRC, file);
          offenders.push(`${rel}:${i + 1}: ${lines[i].trim()}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
