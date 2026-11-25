import { describe, expect, it } from "vitest";
import { PUBLIC_ROUTES } from "../App";

/**
 * The owner's rule (principle 7): ship the manual INSIDE the product so a
 * reader sees it on first open — "no customer reads project docs". A login
 * wall in front of the manual/library would defeat that (#2090). These are
 * static, public-by-design pages; gating is reserved for routes that actually
 * call the credentialed workspace API.
 */
describe("public routes (#2090)", () => {
  it("lets a first-time reader open the manual without credentials", () => {
    expect(PUBLIC_ROUTES).toContain("manual");
  });

  it("lets a first-time reader browse the public world library, reading room and chronicle", () => {
    expect(PUBLIC_ROUTES).toContain("library");
    expect(PUBLIC_ROUTES).toContain("worldbook"); // the reading room holds all 206 scrolls, zero credentialed API calls
    expect(PUBLIC_ROUTES).toContain("chronicle");
  });

  it("keeps the guide and the two public read-only LLM lanes open", () => {
    expect(PUBLIC_ROUTES).toContain("guide");
    expect(PUBLIC_ROUTES).toContain("observe");
    expect(PUBLIC_ROUTES).toContain("ask-the-book");
    expect(PUBLIC_ROUTES).toContain("model-router");
  });

  it("does NOT make credentialed workspace routes public", () => {
    for (const gated of ["dashboard", "eval", "jobs", "identity", "billing", "runbook", "dig"]) {
      expect(PUBLIC_ROUTES).not.toContain(gated);
    }
  });
});
