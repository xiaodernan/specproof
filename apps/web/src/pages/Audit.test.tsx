import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import Audit from "./Audit";
import { ApiError, apiGet, getAuthMe } from "../api";
import { AUDIT_DISPOSITIONS } from "../ui/auditLabels";

// The audit page resolves the principal (admin/auditor gate) and then reads
// GET /api/v1/admin/audit, whose rows carry a server-stamped job_disposition
// (#95). Tests mock the api module and never touch the network.

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return { ...actual, apiGet: vi.fn(), getAuthMe: vi.fn() };
});

const apiGetMock = vi.mocked(apiGet);
const getAuthMeMock = vi.mocked(getAuthMe);

const ROWS = {
  audit: [
    {
      id: 3,
      job_id: "11111111-2222-3333-4444-555555555555",
      actor: "system",
      action: "job_status_transition",
      from_status: "QUEUED",
      to_status: "RUNNING",
      detail: "",
      attempted_tenant: null,
      created_at: "2026-09-26T18:44:31",
      job_disposition: "present",
    },
    {
      id: 2,
      job_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      actor: "lifecycle",
      action: "job_records_deleted",
      from_status: null,
      to_status: null,
      detail: "audit_logs retained by design",
      attempted_tenant: null,
      created_at: "2026-09-26T17:15:20",
      job_disposition: "purged_by_lifecycle",
    },
    {
      id: 1,
      job_id: null,
      actor: "api",
      action: "tenant_isolation_blocked",
      from_status: null,
      to_status: null,
      detail: "",
      attempted_tenant: "t-other",
      created_at: "2026-09-25T21:56:40",
      job_disposition: "system_level",
    },
  ],
  count: 3,
};

beforeEach(() => {
  getAuthMeMock.mockResolvedValue({ principal: { roles: ["auditor"] } } as never);
});

afterEach(() => {
  vi.clearAllMocks();
});

it("glosses every job disposition and keeps the raw token reachable", async () => {
  apiGetMock.mockResolvedValue(ROWS as never);
  render(<Audit />);
  const pills = await screen.findAllByTestId("audit-disposition");
  expect(pills.map((p) => p.textContent)).toEqual([
    AUDIT_DISPOSITIONS.present.label,
    AUDIT_DISPOSITIONS.purged_by_lifecycle.label,
    AUDIT_DISPOSITIONS.system_level.label,
  ]);
  // A disposition is a judgement, so its reason must be attached, not implied
  // by colour: each pill carries the hint as its title.
  for (const pill of pills) expect(pill.getAttribute("title")).toBeTruthy();
  expect(within(pills[1]).getByText(AUDIT_DISPOSITIONS.purged_by_lifecycle.label)).toBeTruthy();
});

it("distinguishes an unavailable audit store from an empty one", async () => {
  apiGetMock.mockRejectedValue(
    new ApiError(
      503,
      "Multi-tenant auth is not enabled: set SPECPROOF_AUTH_ENABLED=true or OIDC_ISSUER",
      "PROVIDER_UNAVAILABLE",
    ),
  );
  render(<Audit />);
  const box = await screen.findByTestId("audit-auth-disabled");
  expect(box.textContent).toContain("不是没有记录");
  expect(box.textContent).toContain("SPECPROOF_AUTH_ENABLED");
  expect(screen.queryByText("最近没有审计记录")).toBeNull();
});

it("renders a server refusal as a refusal, not as no history", async () => {
  apiGetMock.mockRejectedValue(new ApiError(403, "role ['viewer'] is not permitted here", "TENANT_FORBIDDEN"));
  render(<Audit />);
  const denied = await screen.findByTestId("audit-denied");
  expect(denied.textContent).toContain("TENANT_FORBIDDEN".length ? "服务端拒绝" : "");
  expect(denied.textContent).toContain("role ['viewer'] is not permitted here");
});

it("shows the empty state only when the store really answered empty", async () => {
  apiGetMock.mockResolvedValue({ audit: [], count: 0 } as never);
  render(<Audit />);
  expect(await screen.findByText("最近没有审计记录")).toBeTruthy();
  expect(screen.queryByTestId("audit-scope-note")).toBeNull();
});

it("refuses to invent a meaning for an unregistered disposition", async () => {
  apiGetMock.mockResolvedValue({
    audit: [{ ...ROWS.audit[0], id: 9, job_disposition: "quantum_state" }],
    count: 1,
  } as never);
  render(<Audit />);
  const pill = (await screen.findAllByTestId("audit-disposition"))[0];
  expect(pill.textContent).toContain("未登记状态");
  // The unknown token stays visible so an operator can report it verbatim.
  expect(pill.textContent).toContain("quantum_state");
  expect(pill.getAttribute("title")).toContain("词表之外");
});

it("hides the page behind the same role gate the handler uses", async () => {
  getAuthMeMock.mockResolvedValue({ principal: { roles: ["operator"] } } as never);
  render(<Audit />);
  expect(await screen.findByTestId("audit-forbidden")).toBeTruthy();
  // operator is exactly the role the audit endpoint does NOT accept; the copy
  // has to say who does.
  expect(screen.getByTestId("audit-forbidden").parentElement?.textContent).toContain("admin / auditor");
  expect(apiGetMock).not.toHaveBeenCalled();
});

it("says the total is unknown when the server does not answer one", async () => {
  apiGetMock.mockResolvedValue({
    audit: [...ROWS.audit, { ...ROWS.audit[0], id: 77, job_disposition: "unexplained" }],
    count: 4,
  } as never);
  render(<Audit />);
  const note = await screen.findByTestId("audit-scope-note");
  expect(note.textContent).toContain("未回传命中总数");
  // The old sentence claimed a window size; without a total the page may only
  // say what it cannot say.
  expect(note.textContent).not.toContain("已全部显示");
});

it("reports how much history the loaded window does not cover", async () => {
  apiGetMock.mockResolvedValue({ ...ROWS, count: 3, total: 42 } as never);
  render(<Audit />);
  const note = await screen.findByTestId("audit-scope-note");
  expect(note.textContent).toContain("共命中 42 条");
  expect(note.textContent).toContain("另有 39 条未加载");
});

it("says a filtered trail is complete when it is", async () => {
  apiGetMock.mockResolvedValue({ ...ROWS, count: 3, total: 3 } as never);
  render(<Audit />);
  const note = await screen.findByTestId("audit-scope-note");
  expect(note.textContent).toContain("已全部显示");
  expect(note.textContent).not.toContain("未加载");
});

// ── #97: asking about one job ──────────────────────────────────

const JOB = "11111111-2222-3333-4444-555555555555";

beforeEach(() => {
  window.location.hash = "";
});

it("reads the job filter from the deep link and asks the server for it", async () => {
  window.location.hash = "#/audit?job=" + JOB;
  apiGetMock.mockResolvedValue({ ...ROWS, count: 3, total: 3, job_id: JOB, job_present: true } as never);
  render(<Audit />);
  await screen.findAllByTestId("audit-disposition");
  const url = String(apiGetMock.mock.calls[0][0]);
  expect(url).toContain("job_id=" + JOB);
  const note = await screen.findByTestId("audit-filter-note");
  expect(note.textContent).toContain(JOB);
  expect(note.textContent).toContain("作业在册");
  expect(note.querySelector("a")?.getAttribute("href")).toBe("#/jobs/" + JOB);
});

it("keeps the three empty answers apart", async () => {
  // 1. the id matches no job at all — the reader typed it wrong;
  window.location.hash = "#/audit?job=" + JOB;
  apiGetMock.mockResolvedValue({ audit: [], count: 0, total: 0, job_id: JOB, job_present: false } as never);
  const first = render(<Audit />);
  expect(await screen.findByTestId("audit-job-missing")).toBeTruthy();
  expect(screen.getByTestId("audit-job-missing").textContent).toContain(JOB);
  // the unfiltered sentence must not appear under a filter.
  expect(screen.queryByText("最近没有审计记录")).toBeNull();
  first.unmount();
  vi.clearAllMocks();

  // 2. the job exists but has no audit rows;
  window.location.hash = "#/audit?job=" + JOB;
  apiGetMock.mockResolvedValue({ audit: [], count: 0, total: 0, job_id: JOB, job_present: true } as never);
  const second = render(<Audit />);
  expect(await screen.findByTestId("audit-job-no-rows")).toBeTruthy();
  expect(screen.queryByTestId("audit-job-missing")).toBeNull();
  second.unmount();
  vi.clearAllMocks();

  // 3. the server did not probe existence, which is its own answer.
  window.location.hash = "#/audit?job=" + JOB;
  apiGetMock.mockResolvedValue({ audit: [], count: 0, total: 0, job_id: JOB, job_present: null } as never);
  render(<Audit />);
  expect(await screen.findByTestId("audit-job-unknown")).toBeTruthy();
  expect(screen.queryByTestId("audit-job-no-rows")).toBeNull();
});

it("applies a typed job id without a page reload", async () => {
  window.location.hash = "#/audit";
  apiGetMock.mockResolvedValue({ ...ROWS, count: 3, total: 3, job_present: true } as never);
  render(<Audit />);
  await screen.findAllByTestId("audit-disposition");
  expect(String(apiGetMock.mock.calls[0][0])).not.toContain("job_id=");

  fireEvent.change(screen.getByLabelText(/按作业号过滤/), { target: { value: JOB } });
  fireEvent.click(screen.getByRole("button", { name: "查询" }));
  await screen.findByTestId("audit-filter-note");
  const last = String(apiGetMock.mock.calls[apiGetMock.mock.calls.length - 1][0]);
  expect(last).toContain("job_id=" + JOB);
  // 清除筛选 must go back to the whole window, not to an empty filter string.
  fireEvent.click(screen.getByRole("button", { name: "清除筛选" }));
  const cleared = String(apiGetMock.mock.calls[apiGetMock.mock.calls.length - 1][0]);
  expect(cleared).not.toContain("job_id=");
});

it("leaves a malformed job id to the server instead of guessing a copy", async () => {
  // The page sends whatever the reader typed and renders the server's own
  // refusal: re-declaring the id shape here is how #81 drifted.
  window.location.hash = "#/audit?job=not-a-uuid";
  apiGetMock.mockRejectedValue(new ApiError(422, "string does match regex", "VALIDATION_FAILED"));
  render(<Audit />);
  expect(await screen.findByText(/VALIDATION_FAILED/)).toBeTruthy();
  expect(String(apiGetMock.mock.calls[0][0])).toContain("job_id=not-a-uuid");
});
