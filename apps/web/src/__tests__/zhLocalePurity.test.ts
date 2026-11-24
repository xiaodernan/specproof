import { describe, expect, it } from "vitest";

/**
 * Principle 8: in zh mode, prose stays Chinese. Proper nouns, code tokens,
 * quoted English source requirements and named scroll/work titles are allowed;
 * a run of 4+ ordinary English words in a zh value is not — that is a sentence
 * that leaked across the locale boundary (#2089).
 *
 * Sources are pulled in with Vite's `import.meta.glob(..., { query: "?raw" })`:
 * no Node fs/path, so this test typechecks under the browser-only tsconfig.
 */
const SENTENCE = /\b(?:[A-Za-z][a-z]+\s+){3,}[A-Za-z][a-z]+\b/g;
const ALLOW = [
  "pre-existing formatting issues should not block new commits regardless of materiality",
  "existing formatting issues should not block new commits regardless of materiality",
  "the seal and the window",
  "before the reader",
  "open world",
  "state graph",
  "prompt cache",
  "code change",
];

// All .ts/.tsx source under src/ except tests, loaded as raw text.
const sources = import.meta.glob<string>("../**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true });

describe("zh locale purity (#2089)", () => {
  it("has no whole English sentences in zh values", () => {
    const offenders: string[] = [];
    for (const [path, text] of Object.entries(sources)) {
      for (const [i, line] of text.split("\n").entries()) {
        if (!/\bzh\s*:/.test(line)) continue;
        const m = line.match(/zh\s*:\s*["'`]([^"'`]+)["'`]/);
        if (!m) continue;
        for (const hit of m[1].match(SENTENCE) ?? []) {
          const phrase = hit.trim().toLowerCase();
          if (ALLOW.some((a) => phrase.includes(a))) continue;
          offenders.push(`${path}:${i + 1}: ${hit.trim()}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
