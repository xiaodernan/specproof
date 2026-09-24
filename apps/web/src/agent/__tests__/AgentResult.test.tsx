import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import AgentResult from "../pages/AgentResult";
import type { AgentAccept, AgentJob } from "../../api";

// Red-line tests for the independent accept projection (W35.1). The console
// persisted this verdict but never returned it over HTTP, so the result page
// could print "开发完成不等于独立验收通过" while being unable to show the one
// record that separates the two. These cases pin the four states apart:
// not terminal / terminal with no record / a record / an unreadable record.

const baseJob = (over: Partial<AgentJob>): AgentJob => ({
  id: "job-1",
  task_name: "pagination",
  repo_path: "D:/repos/svc",
  spec_text: "add pagination",
  status: "COMPLETED",
  plan: null,
  progress: { percent: 100, current_step: 0, message: "done", updated_at: "2026-08-18T00:00:00Z" },
  result: null,
  accept: null,
  worker_id: "w1",
  created_at: "2026-08-18T00:00:00Z",
  updated_at: "2026-08-18T00:00:00Z",
  events_count: 2,
  approvals_count: 0,
  ...over,
});

function stubJob(job: AgentJob) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/approvals")) {
        return { ok: true, status: 200, json: async () => ({ approvals: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({ job }) };
    })
  );
}

const accept = (over: Partial<AgentAccept>): AgentAccept => ({
  attached: true,
  malformed: false,
  verdict: "BLOCKED",
  note: "",
  ...over,
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AgentResult — 独立验收投影 ACCEPT", () => {
  it("renders a BLOCKED whose gates passed as a missing certificate, not a failed check", async () => {
    stubJob(
      baseJob({
        accept: accept({
          note: "runtime lane: 门禁摘要通过; 完整 accept 闭包 交由 craft accept CLI 执行",
          rolled_back: false,
          gates: {
            overall: "passed",
            overall_note: "all gates passed",
            summary: "GATES: task=pagination overall=passed run_test=passed",
            entries: [
              { gate: "run_test", status: "passed", note: "18 passed", findings_total: 0 },
            ],
            total: 1,
            truncated: false,
          },
        }),
      })
    );
    render(<AgentResult jobId="job-1" />);

    const pill = await screen.findByText("未签发合并证书 BLOCKED", { selector: ".pill" });
    // Amber, never red: this lane cannot issue a certificate, so BLOCKED is
    // its normal happy path and must not read as "你的代码没通过检查".
    expect(pill.className).toBe("pill pill-unverified");
    expect(pill.getAttribute("title")).toBe("BLOCKED");
    expect(screen.getByText(/不代表下方门禁未通过/)).toBeTruthy();
    expect(screen.queryByText(/内部门禁 FAIL/)).toBeNull();
    expect(screen.getByText("相关测试")).toBeTruthy();
    expect(screen.getByText("本次未签发合并证书。")).toBeTruthy();
  });

  it("renders a BLOCKED that came from a failed internal gate as a real failure", async () => {
    // Same token, opposite fact: `_gate_accept_projection` also emits BLOCKED
    // when `gates.overall === "failed"`. Painting that amber and telling the
    // reader "不代表下方门禁未通过" would be a false assurance — the mirror
    // image of the red trap above, and the reason the tone comes from the
    // payload rather than from the verdict token.
    stubJob(
      baseJob({
        accept: accept({
          note: "内部门禁 FAIL: run_test",
          rolled_back: false,
          gates: {
            overall: "failed",
            overall_note: "1 gate failed",
            summary: "GATES: task=pagination overall=failed run_test=failed",
            entries: [
              { gate: "run_test", status: "failed", note: "2 failures", findings_total: 1 },
            ],
            total: 1,
            truncated: false,
          },
          findings: [{ gate: "run_test", detail: "test_page_size" }],
          findings_total: 1,
          findings_truncated: false,
        }),
      })
    );
    render(<AgentResult jobId="job-1" />);

    const pill = await screen.findByText("门禁未通过，未签发合并证书 BLOCKED", { selector: ".pill" });
    expect(pill.className).toBe("pill pill-bad");
    // The note itself and the derived notice both mention 内部门禁 FAIL, so
    // match the notice's own wording.
    expect(screen.getByText(/有门禁未通过/)).toBeTruthy();
    expect(screen.queryByText(/不代表下方门禁未通过/)).toBeNull();
    expect(screen.getByText(/关联发现 1 条/)).toBeTruthy();
  });

  it("refuses to guess why BLOCKED happened when the projection has no gate summary", async () => {
    stubJob(baseJob({ accept: accept({ note: "accept closure reported a blocker" }) }));
    render(<AgentResult jobId="job-1" />);

    const pill = await screen.findByText("未签发合并证书 BLOCKED", { selector: ".pill" });
    expect(pill.className).toBe("pill pill-unverified");
    expect(await screen.findByText(/无法区分/)).toBeTruthy();
    expect(screen.queryByText(/不代表下方门禁未通过/)).toBeNull();
    expect(screen.getByText("该投影不含门禁摘要（例如验收过程本身出错时）。缺摘要不等于全通过。")).toBeTruthy();
  });

  it("shows an issued certificate path as text, and only green for VERIFIED", async () => {
    stubJob(
      baseJob({
        accept: accept({
          verdict: "VERIFIED",
          certificate_path: "/srv/specproof/jobs/job-1/merge-certificate.json",
        }),
      })
    );
    render(<AgentResult jobId="job-1" />);
    const pill = await screen.findByText("已签发合并证书 VERIFIED", { selector: ".pill" });
    expect(pill.className).toBe("pill pill-ok");
    // Match the disclosure line, not the raw-JSON <details> that also carries
    // the path: the point is that a human sees where the certificate is.
    const line = screen.getByText(/^合并证书：/);
    expect(line.textContent).toContain("/srv/specproof/jobs/job-1/merge-certificate.json");
    expect(screen.queryByText("本次未签发合并证书。")).toBeNull();
  });

  it("says a finished job has no acceptance record, and names the command", async () => {
    stubJob(baseJob({ status: "COMPLETED", accept: null }));
    render(<AgentResult jobId="job-1" />);
    expect(await screen.findByText("这次运行还没有独立验收记录。")).toBeTruthy();
    expect(screen.getByText("specproof craft accept --job job-1")).toBeTruthy();
    expect(screen.queryByText(/任务还在处理中/)).toBeNull();
  });

  it("does not claim a missing record while the job is still running", async () => {
    stubJob(baseJob({ status: "EXECUTING", accept: null }));
    render(<AgentResult jobId="job-1" />);
    expect(await screen.findByText("任务尚未进入终态，独立验收还不会运行。")).toBeTruthy();
    // "还没有独立验收记录" reads as a delivery gap; a running job has no gap yet.
    expect(screen.queryByText("这次运行还没有独立验收记录。")).toBeNull();
  });

  it("keeps an unreadable projection distinct from having none", async () => {
    stubJob(baseJob({ accept: { attached: true, malformed: true } }));
    render(<AgentResult jobId="job-1" />);
    expect(await screen.findByText("验收记录读不出来")).toBeTruthy();
    expect(screen.getByText(/不等于“没有验收”/)).toBeTruthy();
    expect(screen.queryByText("这次运行还没有独立验收记录。")).toBeNull();
  });

  it("reports its own truncation instead of letting 20 look like the total", async () => {
    stubJob(
      baseJob({
        accept: accept({
          gates: {
            overall: "passed",
            overall_note: "",
            summary: "",
            entries: [{ gate: "run_test", status: "passed", note: "", findings_total: 0 }],
            total: 25,
            truncated: true,
          },
          findings: [{ id: 1 }],
          findings_total: 25,
          findings_truncated: true,
        }),
      })
    );
    render(<AgentResult jobId="job-1" />);
    const notices = await screen.findAllByText(/共 25 条/);
    // One notice for the gate list, one for the findings list — each must
    // carry its own total rather than the page claiming a single big number.
    expect(notices.length).toBe(2);
  });

  it("says 回滚状态未记录 when the projection never recorded it", async () => {
    stubJob(baseJob({ accept: accept({}) }));
    render(<AgentResult jobId="job-1" />);
    expect(await screen.findByText("回滚状态未记录")).toBeTruthy();
    expect(screen.queryByText("未回滚")).toBeNull();
  });

  it("renders a missing result on a terminal job as pending, not as processing", async () => {
    stubJob(baseJob({ status: "COMPLETED", result: null, accept: null }));
    render(<AgentResult jobId="job-1" />);
    expect(await screen.findByText(/执行结果还没有写入记录/)).toBeTruthy();
    expect(screen.getByText(/不会显示“通过”，也不会显示“失败”/)).toBeTruthy();
    expect(screen.queryByText("任务还在处理中，完成后会在这里显示改动、检查结果和下一步。")).toBeNull();
  });

  it("shares one gate vocabulary between the development result and the accept record", async () => {
    stubJob(
      baseJob({
        result: {
          verdict: "COMPLETED",
          reason: null,
          gates: {
            overall: "passed",
            gates: [
              { gate: "run_build", status: "passed", note: "mvn -o ok" },
              { gate: "custom_gate", status: "needs_review", note: "" },
            ],
          },
        },
      })
    );
    render(<AgentResult jobId="job-1" />);
    expect(await screen.findByText("项目构建")).toBeTruthy();
    const passed = screen.getByText("通过", { selector: ".pill" });
    expect(passed.className).toBe("pill pill-ok");
    // An unseen status is shown verbatim and stays neutral — unknown is not
    // failure, and it is certainly not a pass.
    const unknown = screen.getByText("needs_review", { selector: ".pill" });
    expect(unknown.className).toBe("pill pill-mute");
    expect(screen.getByText("custom_gate")).toBeTruthy();
  });
});
