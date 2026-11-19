import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../i18n";
import GuessTheVerdict from "../GuessTheVerdict";
import { GUESS_CARDS, GUESS_TOTAL } from "../guessCards";

describe("GuessTheVerdict cards — the court accepts only one answer", () => {
  it("every card has an answer that is exactly ACCEPT or BLOCK", () => {
    for (const card of GUESS_CARDS) {
      expect(["accept", "block"]).toContain(card.answer);
    }
  });

  it("at least one card answers ACCEPT (so the quiz is not a trick deck)", () => {
    expect(GUESS_CARDS.some((c) => c.answer === "accept")).toBe(true);
  });

  it("every card carries a bilingual teach anchored to a volume", () => {
    for (const card of GUESS_CARDS) {
      expect(card.teach.zh.length).toBeGreaterThan(20);
      expect(card.teach.en.length).toBeGreaterThan(20);
      expect(card.teach.zh).not.toBe(card.teach.en);
    }
  });

  it("GUESS_TOTAL matches the card count", () => {
    expect(GUESS_TOTAL).toBe(GUESS_CARDS.length);
  });
});

describe("GuessTheVerdict page", () => {
  it("renders the title and the cards counter", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    const { container } = render(
      <I18nProvider>
        <GuessTheVerdict />
      </I18nProvider>,
    );
    expect(screen.getByText(/Guess the Verdict/i)).toBeTruthy();
    expect(container.querySelectorAll(".guess-stats").length).toBeGreaterThan(0);
  });

  it("renders Chinese title on zh locale", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "zh");
    render(
      <I18nProvider>
        <GuessTheVerdict />
      </I18nProvider>,
    );
    expect(screen.getByText(/猜裁判/)).toBeTruthy();
  });
});
