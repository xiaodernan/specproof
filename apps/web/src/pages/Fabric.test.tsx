import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import evidence from "./evidence.json";
import Fabric from "./Fabric";

/**
 * The Fabric is the repo's self-portrait: every node is a real route.
 * These tests pin the portrait's honesty — the weave exists, the ledger
 * card cites only committed evidence, and clicking a thread navigates.
 */
describe("fabric self-portrait", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.location.hash = "";
  });

  it("renders the weave svg with nodes and the full index table", () => {
    const { container } = render(<Fabric />);
    expect(container.querySelector('svg[role="img"]')).not.toBeNull();
    expect(container.querySelectorAll(".fabric-node").length).toBeGreaterThanOrEqual(30);
    expect(screen.getAllByRole("button").length).toBeGreaterThanOrEqual(30);
  });

  it("chip click navigates to the real route", () => {
    render(<Fabric />);
    fireEvent.click(screen.getByRole("button", { name: /Verifications/ }));
    expect(window.location.hash).toBe("#/jobs");
  });

  it("renders the git evidence card without claiming live traffic", () => {
    const { container } = render(<Fabric />);
    const card = container.querySelector(".fabric-evidence");
    expect(card).not.toBeNull();
    const latest = evidence.latest as { file: string; verdict: string };
    expect(card?.textContent ?? "").toContain(latest.file);
    // The verdict must come verbatim from the committed JSON — never from a fixed string.
    expect(card?.textContent ?? "").toContain(latest.verdict);
    const ledger = container.querySelector(".fabric-stress");
    expect(ledger).not.toBeNull();
    expect(ledger?.textContent ?? "").toMatch(/2026-11-16/);
  });
});
