import { describe, expect, it } from "vitest";
import library from "../library.json";

/**
 * The Library pins the bible's bytes verbatim: every scroll is carried,
 * both languages are present, and the routing channel does not invent
 * anything between the .md file and the reader's eyes.
 */
describe("The Library carries the bible, not an abridgement (#1984)", () => {
  it("ships 183 scrolls in both languages", () => {
    expect(library.count).toBe(199);
    expect(library.zh).toHaveLength(199);
    expect(library.en).toHaveLength(199);
  });

  it("quotes the bible verbatim — scroll zero's opening sentence actually exists in the file", () => {
    expect(library.zh[0].excerpt).toContain("世人写代码");
    expect(library.en[0].excerpt).toContain("arrows");
  });

  it("matches the heading shape of every scroll entry (num+title), including appendices", () => {
    for (const scroll of library.zh) {
      expect(scroll.num).toMatch(/^(卷|附录|终章)/);
      expect(scroll.title.length).toBeGreaterThan(0);
    }
    for (const scroll of library.en) {
      expect(scroll.num).toMatch(/^(Scroll|Volume|Appendix|Final)/);
      expect(scroll.title.length).toBeGreaterThan(0);
    }
  });
});
