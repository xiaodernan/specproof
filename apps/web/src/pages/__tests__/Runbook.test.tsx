import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import Runbook from "../Runbook";
import { I18nProvider } from "../../i18n";

/**
 * /runbook — the model triangulates a firing alert from this repo's facts.
 * Fail-closed parity with every other admin panel. Never a fabricated triage;
 * INCONCLUSIVE is a legitimate answer.
 */
const access = { checked: true, canManage: true };
vi.mock("../../identity/useIdentityAccess", () => ({
  useIdentityAccess: () => access,
}));

const fetchAlerts = vi.fn();
const postRunbook = vi.fn();
vi.mock("../../api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    fetchRunbookAlerts: () => fetchAlerts(),
    postRunbookTriage: (...args: unknown[]) => postRunbook(...args),
  };
});

describe("runbook · on-call triage panel", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem("specproof_locale", "en");
    access.checked = true;
    access.canManage = true;
    fetchAlerts.mockReset();
    postRunbook.mockReset();
    fetchAlerts.mockResolvedValue({
      alerts: ["SpecproofApiDown"],
    });
  });

  it("renders the deployed alerts and fires the triage on ask", async () => {
    postRunbook.mockResolvedValue({
      alert: "SpecproofApiDown",
      verdict: "CONFIRMED",
      findings: [
        { role: "explorer", claim: "The api target is down per an alert rule you touched.", evidence: "facts-pack", confidence: 0.6 },
      ],
      agents: [
        { name: "investigate_explorer", role: "explorer", outcome: "ok", tokens: 7954 },
      ],
      total_tokens_used: 7954,
      generation_time_ms: 41567,
      cached: false,
    });
    const { container } = render(
      <I18nProvider>
        <Runbook />
      </I18nProvider>,
    );
    await waitFor(() => expect(container.textContent).toContain("SpecproofApiDown"));
    const button = screen.getByRole("button", { name: /Run the investigation/i });
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);
    await waitFor(() => expect(container.textContent).toContain("CONFIRMED"));
    expect(container.textContent).toContain("api target");
  });

  it("shows an honest error when the model is unavailable, never a fabricated triage", async () => {
    postRunbook.mockRejectedValue(new Error("The model lane could not be consulted."));
    const { container } = render(
      <I18nProvider>
        <Runbook />
      </I18nProvider>,
    );
    await waitFor(() => expect(container.textContent).toContain("SpecproofApiDown"));
    const button = screen.getByRole("button", { name: /Run the investigation/i });
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);
    await waitFor(() => expect(container.textContent).toContain("could not be consulted"));
  });

  it("does not render the triage for non-admins (fail-closed parity)", () => {
    access.canManage = false;
    const { container } = render(
      <I18nProvider>
        <Runbook />
      </I18nProvider>,
    );
    expect(container.textContent).toContain("admin/operator");
    expect(container.textContent).not.toContain("Run the investigation");
  });
});
