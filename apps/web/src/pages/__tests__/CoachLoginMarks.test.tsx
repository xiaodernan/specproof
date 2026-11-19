/**
 * The landing surface was the one page nobody's data-coach reached: every
 * mark lived on the authenticated shell, and this page is what the static
 * demo (and every first-time visitor) actually sees — so the teaching layer
 * reported "0 处按键与操作，皆已标出" on the page it mattered most.
 *
 * These legs pin the three hero marks to the COACH_MARKS registry:
 *
 *   hero.brand  – the logo carries the cohort to the guide;
 *   hero.guide  – the copy of the book itself;
 *   hero.connect – the button that opens (or deliberately fails, on the
 *                  static demo) the real verification loop.
 *
 * A fourth hook appears and this file fails with the name of the missing
 * registry entry; a brand new hero CTA without a registry row fails the same
 * way. Neither failure is subtle, neither is allowed to drift.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render } from "@testing-library/react";
import Login from "../Login";
import { COACH_MARKS, readCoachEnabled } from "../../ui/coachData";

function response(status: number, data: unknown) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

describe("landing teaching layer", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
    window.location.hash = "#/login";
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("hero marks land on the registry", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => response(200, { auth_mode: "legacy", oidc: { enabled: false } })),
    );
    await act(async () => {
      render(<Login />);
    });
    const hooks = Array.from(document.querySelectorAll("[data-coach]")).map((el) =>
      el.getAttribute("data-coach"),
    );
    for (const key of ["hero.brand", "hero.guide", "hero.connect"]) {
      expect(hooks).toContain(key);
    }
    const registered = new Set(COACH_MARKS.map((mark) => mark.key));
    for (const key of hooks) {
      expect(registered.has(key ?? "")).toBe(true);
    }
  });

  it("first visit defaults the teaching layer to ON", () => {
    expect(readCoachEnabled()).toBe(true);
  });

  it("explicit dissent cancels it", () => {
    window.localStorage.setItem("specproof_coach_marks", "0");
    expect(readCoachEnabled()).toBe(false);
  });
});
