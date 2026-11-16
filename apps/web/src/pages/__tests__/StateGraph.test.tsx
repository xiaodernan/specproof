import { describe, expect, it } from "vitest";
import { render, cleanup } from "@testing-library/react";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../i18n";
import { CONCEPTS, GRAPHS } from "../stategraph.copy";
import StateGraph from "../StateGraph";

/**
 * The State Graphs page teaches LangGraph's StateGraph by pointing at the
 * six graphs this repository actually runs. Every claim it makes is either
 * a concept note about LangGraph as used here, or a byte visible in the same
 * repo (file names, state fields, verdict lexicon).
 *
 * One of the six is networked on purpose: cache_witness strikes this host's
 * model lane to count the prefix cache. The page must say so — never let the
 * browser learn to phone home through this book.
 */
describe("StateGraph — LangGraph as wired in this repository", () => {
  it("renders both locales with all eight concept terms and six graphs", () => {
    for (const locale of ["zh", "en"] as const) {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { container } = render(
        <I18nProvider>
          <StateGraph />
        </I18nProvider>,
      );
      for (const concept of CONCEPTS) {
        expect(container.textContent).toContain(concept.term[locale]);
      }
      for (const graph of GRAPHS) {
        expect(container.textContent).toContain(graph.file);
        expect(container.textContent).toContain(graph.stateName);
        for (const node of graph.chain) {
          expect(container.textContent).toContain(node);
        }
      }
      cleanup();
    }
  });

  it("quotes the live composite verdict verbatim from night_watch.json", () => {
    for (const locale of ["zh", "en"] as const) {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { container } = render(
        <I18nProvider>
          <StateGraph />
        </I18nProvider>,
      );
      const nightWatch = GRAPHS.find((g) => g.id === "night_watch");
      expect(nightWatch?.live).toBeTruthy();
      expect(container.textContent).toContain("REGRESSION");
      expect(container.textContent).toContain("CRACKED");
      cleanup();
    }
  });

  it("quotes the cache-witness verdict verbatim from cache_witness.json (HIT · 4224 ×2)", () => {
    for (const locale of ["zh", "en"] as const) {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { container } = render(
        <I18nProvider>
          <StateGraph />
        </I18nProvider>,
      );
      const witness = GRAPHS.find((g) => g.id === "cache_witness");
      expect(witness?.live).toBeTruthy();
      expect(witness?.file).toBe("agent/graphs/cache_witness_graph.py");
      expect(witness?.chain).toEqual(["intake", "strike_one", "strike_two", "verdict", "report", "END"]);
      // the numbers on the cards come from the tracked cache_witness.json, verbatim
      expect(container.textContent).toContain("4224");
      expect(container.textContent).toContain("HIT");
      expect(container.textContent).toContain("95.3");
      cleanup();
    }
  });

  it("does not let the networked graph wear an offline colophon", () => {
    for (const locale of ["zh", "en"] as const) {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { container } = render(
        <I18nProvider>
          <StateGraph />
        </I18nProvider>,
      );
      // the colophon must name the exception, not erase it
      expect(container.textContent).toContain("cache_witness");
      expect(container.textContent).not.toContain("six graphs run offline; none");
      cleanup();
    }
  });

  it("does not fake a green lamp — the page never upgrades CRACKED to CLEAR", () => {
    const nightWatchBlock = GRAPHS.find((g) => g.id === "night_watch");
    expect(nightWatchBlock?.live?.en).toContain("CRACKED");
  });
});
