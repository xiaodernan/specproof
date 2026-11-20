import { describe, expect, it } from "vitest";
import { render, cleanup } from "@testing-library/react";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../i18n";
import { CONCEPTS, GRAPHS } from "../stategraph.copy";
import StateGraph from "../StateGraph";

/**
 * The State Graphs page teaches LangGraph's StateGraph by pointing at the
 * fifteen graphs this repository actually runs. Every claim it makes is either
 * a concept note about LangGraph as used here, or a byte visible in the same
 * repo (file names, state fields, verdict lexicon).
 *
 * Eight of the fifteen go out by design or on an explicit --live: cache_witness
 * strikes this host's model lane to count the prefix cache, insight_advice
 * strikes the /insight Advice lane to witness it answering at all,
 * investigation_dig strikes the model on purpose as a readonly workspace digger,
 * runbook_triage strikes the model to answer one on-call alert from repo facts,
 * ask_the_book / next_step / stress_digest strike only under an explicit --live.
 * covenant_witness stays offline forever — it hashes bytes, never a prompt.
 * The page must say so — it must never let the browser learn to
 * phone home through this book, and never let a judge call hide behind a
 * witness's name.
 */
describe("StateGraph — LangGraph as wired in this repository", () => {
  it("documents the model-driven router's conditional edges (the LLM chooses the next state)", () => {
    const router = GRAPHS.find((g) => g.id === "model_router");
    expect(router).toBeTruthy();
    expect(router?.file).toBe("agent/graphs/model_router_graph.py");
    // The distinguishing feature: a conditional edge whose branch is the model's route label.
    expect(router?.chain).toContain("route");
    expect(router?.chain.some((n) => n.includes("evidence") && n.includes("nextstep"))).toBe(true);
    for (const locale of ["zh", "en"] as const) {
      expect(router?.role[locale].length).toBeGreaterThan(40);
      expect(router?.live?.[locale]).toBeTruthy();
    }
  });

  it("renders both locales with all eight concept terms and fifteen graphs", () => {
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

  it("quotes the advice-lane witness verbatim from insight_advice_witness.json (ANSWERED)", () => {
    for (const locale of ["zh", "en"] as const) {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { container } = render(
        <I18nProvider>
          <StateGraph />
        </I18nProvider>,
      );
      const witness = GRAPHS.find((g) => g.id === "insight_advice");
      expect(witness?.live).toBeTruthy();
      expect(witness?.file).toBe("agent/graphs/insight_advice_graph.py");
      expect(witness?.chain).toEqual(["intake", "strike", "verdict", "report", "END"]);
      expect(container.textContent).toContain("insight_advice_graph.py");
      expect(container.textContent).toContain("ANSWERED");
      expect(container.textContent).toContain("730");
      cleanup();
    }
  });

  it("quotes the offline ledger witness verbatim from usage_ledger_witness.json (ANSWERED · 84 rows)", () => {
    for (const locale of ["zh", "en"] as const) {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { container } = render(
        <I18nProvider>
          <StateGraph />
        </I18nProvider>,
      );
      const witness = GRAPHS.find((g) => g.id === "usage_ledger");
      expect(witness?.live).toBeTruthy();
      expect(witness?.file).toBe("agent/graphs/usage_ledger_graph.py");
      expect(witness?.chain).toEqual(["intake", "strike", "verdict", "report", "END"]);
      expect(witness?.live).toBeTruthy();
      expect(container.textContent).toContain("usage_ledger_graph.py");
      expect(container.textContent).toContain("ANSWERED");
      expect(container.textContent).toContain("84");
      cleanup();
    }
  });

  it("quotes the networked investigator verbatim from investigation_dig.json (EVIDENCE-GATHERED)", () => {
    for (const locale of ["zh", "en"] as const) {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { container } = render(
        <I18nProvider>
          <StateGraph />
        </I18nProvider>,
      );
      const witness = GRAPHS.find((g) => g.id === "investigation_dig");
      expect(witness?.live).toBeTruthy();
      expect(witness?.file).toBe("agent/graphs/investigation_dig_graph.py");
      expect(witness?.chain).toEqual(["intake", "strike", "verdict", "report", "END"]);
      expect(container.textContent).toContain("investigation_dig_graph.py");
      expect(container.textContent).toContain("EVIDENCE-GATHERED");
      cleanup();
    }
  });

  it("quotes the networked on-call triage verbatim from runbook_triage.json (CONFIRMED)", () => {
    for (const locale of ["zh", "en"] as const) {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { container } = render(
        <I18nProvider>
          <StateGraph />
        </I18nProvider>,
      );
      const witness = GRAPHS.find((g) => g.id === "runbook_triage");
      expect(witness?.live).toBeTruthy();
      expect(witness?.file).toBe("agent/graphs/runbook_triage_graph.py");
      expect(witness?.chain).toEqual(["intake", "strike", "verdict", "report", "END"]);
      expect(container.textContent).toContain("runbook_triage_graph.py");
      expect(container.textContent).toContain("CONFIRMED");
      cleanup();
    }
  });

  it("quotes the covenant-witness verbatim from covenant_witness.json (HELD · pinned · 1450 B)", () => {
    for (const locale of ["zh", "en"] as const) {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { container } = render(
        <I18nProvider>
          <StateGraph />
        </I18nProvider>,
      );
      const witness = GRAPHS.find((g) => g.id === "covenant_witness");
      expect(witness?.live).toBeTruthy();
      expect(witness?.file).toBe("agent/graphs/covenant_witness_graph.py");
      expect(witness?.chain).toEqual(["intake", "verify", "verdict", "report", "END"]);
      expect(container.textContent).toContain("covenant_witness_graph.py");
      expect(container.textContent).toContain("HELD");
      expect(container.textContent).toContain("1450");
      cleanup();
    }
  });

  it("quotes the exhibit-copilot verbatim from exhibit_copilot.json (HELD · pinned)", () => {
    for (const locale of ["zh", "en"] as const) {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { container } = render(
        <I18nProvider>
          <StateGraph />
        </I18nProvider>,
      );
      const copilot = GRAPHS.find((g) => g.id === "exhibit_copilot");
      expect(copilot?.live).toBeTruthy();
      expect(copilot?.file).toBe("agent/graphs/exhibit_copilot_graph.py");
      expect(copilot?.chain).toEqual(["intake", "strike", "verify", "verdict", "report", "END"]);
      expect(container.textContent).toContain("exhibit_copilot_graph.py");
      expect(container.textContent).toContain("HELD");
      expect(container.textContent).toContain("pinned=true");
      cleanup();
    }
  });

  it("does not let the networked graphs wear an offline colophon — names them", () => {
    for (const locale of ["zh", "en"] as const) {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { container } = render(
        <I18nProvider>
          <StateGraph />
        </I18nProvider>,
      );
      expect(container.textContent).toContain("cache_witness");
      expect(container.textContent).toContain("insight_advice");
      expect(container.textContent).toContain("investigation_dig");
      expect(container.textContent).toContain("runbook_triage");
      expect(container.textContent).toContain("covenant_witness");
      expect(container.textContent).toContain("exhibit_copilot");
      expect(container.textContent).not.toContain("all seven run offline");
      expect(container.textContent).not.toContain("all eight run offline");
      expect(container.textContent).not.toContain("all nine run offline");
      expect(container.textContent).not.toContain("all ten run offline");
      expect(container.textContent).toContain("usage_ledger");
      cleanup();
    }
  });

  it("does not fake a green lamp — the page never upgrades CRACKED to CLEAR", () => {
    const nightWatchBlock = GRAPHS.find((g) => g.id === "night_watch");
    expect(nightWatchBlock?.live?.en).toContain("CRACKED");
  });
});
