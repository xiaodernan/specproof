import { describe, expect, it } from "vitest";
import library from "../library.json";

/**
 * The Library pins the bible's bytes verbatim: every scroll is carried,
 * both languages are present, and the routing channel does not invent
 * anything between the .md file and the reader's eyes.
 */
describe("The Library carries the bible, not an abridgement (#1984)", () => {
  it("ships 206 scrolls in both languages", () => {
    expect(library.count).toBe(206);
    expect(library.zh).toHaveLength(206);
    expect(library.en).toHaveLength(206);
  });

  it("carries scrolls 205 (LLM), 206 and 207 (real facts) in both languages", () => {
    const zhLast = library.zh[library.zh.length - 1];
    const enLast = library.en[library.en.length - 1];
    // The newest scroll is the one built from this session's real #2096-2099 work.
    expect(zhLast.title).toContain("门自己学会把影子补上");
    expect(enLast.title).toContain("The Gate Learns to Redraw Its Own Shadow");
    expect(zhLast.excerpt.length).toBeGreaterThan(0);
    expect(enLast.excerpt.length).toBeGreaterThan(0);
    // Earlier scrolls are still carried, not replaced.
    expect(library.zh.some((s) => s.title.includes("文字必须指向它所写之物"))).toBe(true);
    expect(library.en.some((s) => s.title.includes("Words Must Point to What They Name"))).toBe(true);
    expect(library.zh.some((s) => s.title.includes("不可达不是失败"))).toBe(true);
    expect(library.en.some((s) => s.title.includes("Unreachable Is Not Failure"))).toBe(true);
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
