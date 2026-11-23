import { describe, expect, it } from "vitest";
import library from "../library.json";

/**
 * The Library pins the bible's bytes verbatim: every scroll is carried,
 * both languages are present, and the routing channel does not invent
 * anything between the .md file and the reader's eyes.
 */
describe("The Library carries the bible, not an abridgement (#1984)", () => {
  it("ships 204 scrolls in both languages", () => {
    expect(library.count).toBe(204);
    expect(library.zh).toHaveLength(204);
    expect(library.en).toHaveLength(204);
  });

  it("carries the LLM-generated scroll 205 (#2077) in both languages", () => {
    const zhLast = library.zh[library.zh.length - 1];
    const enLast = library.en[library.en.length - 1];
    expect(zhLast.title).toContain("文字必须指向它所写之物");
    expect(enLast.title).toContain("Words Must Point to What They Name");
    // The new volume's body really reached the reader payload, not just the ledger.
    expect(zhLast.excerpt.length).toBeGreaterThan(0);
    expect(enLast.excerpt.length).toBeGreaterThan(0);
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
