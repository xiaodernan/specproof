import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../i18n";
import Gestures from "../Gestures";
import { GESTURES } from "../gestures.copy";

describe("Fourteen Gestures page", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    window.localStorage.clear();
  });

  it("renders all fourteen stances and the first one in detail by default (zh)", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "zh");
    render(
      <I18nProvider>
        <Gestures />
      </I18nProvider>,
    );
    expect(screen.getByText("验收官十四式", { exact: false })).toBeTruthy();
    // all 14 cards render (name + token each)
    for (const gesture of GESTURES) {
      expect(screen.getByLabelText(gesture.zhName + " · " + gesture.token)).toBeTruthy();
    }
    // detail panel shows the poer selected (first) gesture
    expect(screen.getByText("印章盖下去的正脸")).toBeTruthy();
  });

  it("collects a face into localStorage and uncollects on second tap", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "zh");
    render(
      <I18nProvider>
        <Gestures />
      </I18nProvider>,
    );
    const button = screen.getByLabelText("挑衅 · BLOCKED");
    fireEvent.click(button);
    expect(window.localStorage.getItem("specproof_gestures_v1")).toContain("provoke");
    expect(screen.getByText("1 / 14")).toBeTruthy();
    fireEvent.click(button);
    expect(window.localStorage.getItem("specproof_gestures_v1")).toBe("[]");
  });

  it("renders fully in English when the locale says so", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    render(
      <I18nProvider>
        <Gestures />
      </I18nProvider>,
    );
    expect(screen.getAllByText("Fourteen Gestures", { exact: false }).length).toBeGreaterThan(0);
    expect(screen.queryByText("验收官十四式", { exact: false })).toBeNull();
    expect(screen.getByText("The face the seal lands on")).toBeTruthy();
  });
});
