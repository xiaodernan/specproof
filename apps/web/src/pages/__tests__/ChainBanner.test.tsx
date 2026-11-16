import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../i18n";
import ChainBanner from "../ChainBanner";
import auditChain from "../audit_chain.json";

/**
 * The audit-chain roll-call banner: it must always be drawn straight from
 * audit_chain.json — the same file the gazette, the archive and the engine
 * read — and the CLEAR case must paint the jade variant, never the red one.
 */
describe("ChainBanner — one live audit roll-call, five lamps, no inventions", () => {
  it("paints the jade variant and counts the lanes verbatim when the chain is CLEAR", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "zh");
    const { container } = render(
      <I18nProvider>
        <ChainBanner />
      </I18nProvider>,
    );
    const aside = container.querySelector(".chain-banner") as HTMLElement;
    expect(aside).toBeTruthy();
    expect(aside.classList.contains("chain-banner-ok")).toBe(true);
    expect(aside.classList.contains("chain-banner-bad")).toBe(false);
    const banner = aside.textContent ?? "";
    expect(banner).toContain((auditChain as { verdict: string }).verdict);
    expect(banner).toContain(String((auditChain as { lane_count: number }).lane_count));
    expect(banner).toContain("审计链");
    const cta = screen.getByRole("link");
    expect(cta.getAttribute("href")).toBe("#/archive");
  });

  it("speaks English when the locale says so — no Chinese leaking into the en lane", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    const { container } = render(
      <I18nProvider>
        <ChainBanner />
      </I18nProvider>,
    );
    expect(container.textContent).toContain("audit chain");
    expect(container.textContent).not.toContain("审计链");
  });
});
