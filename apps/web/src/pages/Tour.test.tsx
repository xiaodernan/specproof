import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import Tour from "./Tour";

/**
 * Tour is the funnel every newcomer passes through. These tests pin the
 * safety invariants rather than the art: seals cannot be affixed before a
 * station was visited, the rail counts five to six, and storage corruption
 * never crashes the page.
 */
describe("grand tour", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders a progress rail that starts from zero", () => {
    render(<Tour />);
    const rail = screen.getByRole("progressbar");
    expect(rail.getAttribute("aria-valuenow")).toBe("0");
  });

  it("shows all six stations as headings", () => {
    render(<Tour />);
    expect(screen.getAllByRole("heading", { level: 2 }).length).toBeGreaterThanOrEqual(6);
  });

  it("keeps every seal behind the visit gate on a fresh browser", () => {
    const { container } = render(<Tour />);
    expect(container.querySelectorAll(".tour-actions button[disabled]").length).toBe(6);
    expect(screen.queryAllByRole("status").length).toBe(6);
  });

  it("survives corrupted tour storage instead of crashing", () => {
    window.localStorage.setItem("specproof_tour_v1", "{not-json");
    expect(() => render(<Tour />)).not.toThrow();
  });
});
