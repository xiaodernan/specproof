import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import Insight from "./Insight";

/**
 * Insight Deck is RBAC-gated; it NEVER opens via "123". These tests pin both
 * sides of the fail-closed door, plus the honesty of the local-only heat
 * panel: it renders this browser's real tap climate and can erase it.
 */

const access = { checked: true, canManage: false };
vi.mock("../identity/useIdentityAccess", () => ({
  useIdentityAccess: () => access,
}));

const HEAT_KEY = "specproof_heat_v1";
const ACK_KEY = "specproof_heat_ack_v1";

describe("insight deck RBAC", () => {
  beforeEach(() => {
    window.localStorage.clear();
    access.checked = true;
    access.canManage = false;
  });

  it("keeps the deck shut for non-admins (fail-closed, no password bypass)", () => {
    render(<Insight />);
    expect(document.querySelector(".insight-page")).toBeNull();
    expect(screen.queryAllByText(/RBAC fail-closed/i).length).toBeGreaterThanOrEqual(1);
  });

  it("waits for the role check before deciding anything", () => {
    access.checked = false;
    const { container } = render(<Insight />);
    expect(container.querySelector(".insight-spinner")).not.toBeNull();
  });

  it("admits admins and labels the cohort as synthetic", () => {
    access.canManage = true;
    render(<Insight />);
    expect(document.querySelector(".insight-page")).not.toBeNull();
    expect(screen.queryAllByText(/SYNTHETIC COHORT|合成校准数据/i).length).toBeGreaterThanOrEqual(1);
  });

  it("renders the real local heat panel for admins and erases it on demand", () => {
    access.canManage = true;
    window.localStorage.setItem(
      HEAT_KEY,
      JSON.stringify([
        { t: "view", path: "/tour", at: 1 },
        { t: "dwell", path: "/tour", ms: 9000, at: 9001 },
        { t: "rage", target: "button.btn|Go", path: "/tour", at: 9002 },
      ]),
    );
    render(<Insight />);
    expect(document.querySelector(".insight-heat-panel")).not.toBeNull();
    expect(screen.queryAllByText(/button.btn\|Go/i).length).toBeGreaterThanOrEqual(1);
    fireEvent.click(screen.getByRole("button", { name: /清空本机轨迹|Clear this browser's trace/i }));
    expect(window.localStorage.getItem(HEAT_KEY)).toBeNull();
    expect(document.querySelector(".insight-heat-panel")?.textContent ?? "").toMatch(/还没有任何敲击记录|No taps recorded/);
  });

  it("stores only a count when the admin acknowledges the rage report", () => {
    access.canManage = true;
    window.localStorage.setItem(HEAT_KEY, "[]");
    window.localStorage.setItem(ACK_KEY, "3");
    render(<Insight />);
    expect(window.localStorage.getItem(ACK_KEY)).toBe("3");
  });

  it("renders the debt ledger panel reading unsigned.json — signature/current verbatim, no dressing", () => {
    access.canManage = true;
    render(<Insight />);
    const panel = document.querySelector(".insight-debt-panel") as HTMLElement;
    expect(panel).not.toBeNull();
    expect(panel.textContent).toContain("observability-signature");
    expect(panel.textContent).toContain("signature-block-found");
    expect(panel.textContent).toContain("weekly-stress-merged");
    expect(panel.textContent).toContain("port-8000-answers");
    expect(panel.textContent).toContain("branch-cleanliness");
  });

  it("keeps the debt ledger shut for non-admins (fail-closed parity)", () => {
    access.canManage = false;
    render(<Insight />);
    expect(document.querySelector(".insight-debt-panel")).toBeNull();
  });
});
