import { describe, expect, it } from "vitest";
import robots from "../../public/robots.txt?raw";

/**
 * Lighthouse 2026-11-24 measured SEO 0.8 on the worldbook route with a single
 * failure — "robots.txt is not valid": the SPA server answered /robots.txt with
 * index.html, which a crawler cannot parse. A committed, syntactically valid
 * robots.txt at public/ is copied verbatim into dist/ by Vite and served at the
 * origin root. This gate keeps it valid and keeps the public SPA crawlable
 * while backend/data endpoints stay out of indexes.
 */
describe("robots.txt (#2092)", () => {
  it("declares a user-agent and allows the public SPA", () => {
    expect(robots).toMatch(/User-agent:\s*\*/);
    expect(robots).toMatch(/Allow:\s*\//);
  });

  it("keeps backend and telemetry endpoints out of indexes", () => {
    expect(robots).toMatch(/Disallow:\s*\/api\//);
    expect(robots).toMatch(/Disallow:\s*\/v1\//);
    expect(robots).toMatch(/Disallow:\s*\/metrics/);
  });

  it("has no malformed blank directive lines", () => {
    const bad = robots.split(/\r?\n/).filter((l) => l.trim() && !/^\s*#/.test(l) && !/^\s*$/.test(l) && !/^(User-agent|Allow|Disallow|Sitemap|Crawl-delay):/.test(l));
    expect(bad).toEqual([]);
  });
});
