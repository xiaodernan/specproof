import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import Dig from "../Dig";
import { I18nProvider } from "../../i18n";

/**
 * /dig — ask three readonly investigators a question about this repo.
 * Fail-closed parity with every other admin panel (visible to admin/operator
 * only). The model is asked; evidence is shown when the model answers; an
 * honest error path is followed on failure — never a fabricated investigation.
 */

const access = { checked: true, canManage: true };
vi.mock("../../identity/useIdentityAccess", () => ({
  useIdentityAccess: () => access,
}));

const dig = vi.fn();
vi.mock("../../api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    postInvestigationDig: (...args: unknown[]) => dig(...args),
  };
});

describe("dig · investigation panel", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem("specproof_locale", "en");
    access.checked = true;
    access.canManage = true;
    dig.mockReset();
  });

  it("renders for admins and fires a verdict with evidence on ask", async () => {
    dig.mockResolvedValue({
      question: "what is this?",
      verdict: "EVIDENCE-GATHERED",
      findings: [
        { role: "explorer", claim: "A verification platform for AI-diff code.", evidence: "README digest", confidence: 0.9 },
      ],
      agents: [
        { name: "investigate_explorer", role: "explorer", outcome: "ok", tokens: 4200 },
        { name: "investigate_tester",   role: "tester",   outcome: "ok", tokens: 3000 },
        { name: "investigate_security", role: "security", outcome: "ok", tokens: 2500 },
      ],
      total_tokens_used: 9700,
      generation_time_ms: 12000,
      cached: false,
    });
    const { container } = render(
      <I18nProvider>
        <Dig />
      </I18nProvider>,
    );
    const btn = screen.getByRole("button", { name: /Send the investigators/i });
    fireEvent.click(btn);
    await waitFor(() => expect(container.textContent).toContain("EVIDENCE-GATHERED"));
    expect(container.textContent).toContain("verification platform");
  });

  it("shows an honest error when the model is unavailable, never fabricated findings", async () => {
    dig.mockRejectedValue(new Error("模型暂时不可用。"));
    const { container } = render(
      <I18nProvider>
        <Dig />
      </I18nProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: /Send the investigators/i }));
    await waitFor(() => expect(container.textContent).toContain("模型暂时不可"));
  });

  it("does not render the dig panel for non-admins (fail-closed parity)", () => {
    access.canManage = false;
    const { container } = render(
      <I18nProvider>
        <Dig />
      </I18nProvider>,
    );
    expect(container.textContent).toContain("admin / operator");
    expect(container.textContent).not.toContain("Send the investigators");
  });
});
