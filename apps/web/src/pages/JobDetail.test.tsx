import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import JobDetail from "./JobDetail";
import { apiGet, openProgressStream } from "../api";

vi.mock("../api", () => ({ apiGet: vi.fn(), openProgressStream: vi.fn(), downloadCapsule: vi.fn() }));
const get = vi.mocked(apiGet);
const open = vi.mocked(openProgressStream);
const close = vi.fn();
beforeEach(() => { get.mockReset(); open.mockReset(); close.mockReset(); open.mockReturnValue(close); });
afterEach(() => { vi.useRealTimers(); });

describe("verification lifecycle", () => {
  it("keeps the job and actionable errors visible if result services fail", async () => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/failed-job") return { job: { id: "failed-job", status: "ERROR", last_error: "Repository not found", repo_path: "/missing" } };
      throw new Error("Artifacts unavailable");
    }) as typeof apiGet);
    render(<JobDetail jobId="failed-job" />);
    await screen.findByText("执行遇到错误");
    expect(screen.getByText(/Repository not found/)).toBeTruthy();
    expect(screen.getByText(/部分验证结果暂时无法读取/)).toBeTruthy();
    expect(open).not.toHaveBeenCalled();
    expect(get.mock.calls.some(([path]) => path.endsWith("/certificate"))).toBe(false);
  });

  it("diagnoses a known worker last_error in Chinese, keeping the raw string on hover", async () => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/ref-error-job") return { job: { id: "ref-error-job", status: "FAILED", last_error: "fatal: ambiguous argument 'nope': unknown revision or path not in the working tree", repo_path: "/project" } };
      throw new Error("Artifacts unavailable");
    }) as typeof apiGet);
    render(<JobDetail jobId="ref-error-job" />);
    await screen.findByText(/版本引用无法解析/);
    expect(screen.queryByText(/ambiguous argument/)).toBeNull();
    const box = [...document.querySelectorAll(".errorbox")].find((el) => /ambiguous argument/.test(el.getAttribute("title") || ""));
    expect(box?.getAttribute("title")).toMatch(/ambiguous argument/);
  });

  it("refreshes final results and closes live progress after completion", async () => {
    vi.useFakeTimers();
    let status = "RUNNING";
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/job-1") return { job: { id: "job-1", status, repo_path: "/project" } };
      if (path.endsWith("/summary")) return { summary: status === "VERIFIED" ? { verdict: "VERIFIED", contracts_total: 3, matrix_passed: 3 } : {} };
      if (path.endsWith("/stages")) return { job_id: "job-1", stages: [], event_count: 0, degraded: false };
      return { job_id: "job-1", findings: [], count: 0, degraded: false };
    }) as typeof apiGet);
    render(<JobDetail jobId="job-1" />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByText("正在检查代码与需求")).toBeTruthy();
    status = "VERIFIED";
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(screen.getByText("本次验证通过")).toBeTruthy();
    expect(close).toHaveBeenCalledOnce();
    const calls = get.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(20000); });
    expect(get).toHaveBeenCalledTimes(calls);
  });

  it("renders the headline verdict as a Chinese label, not the raw enum", async () => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/job-1") return { job: { id: "job-1", status: "BLOCKED" } };
      if (path.endsWith("/summary")) return { summary: { verdict: "BLOCKED", contracts_total: 4, matrix_failed: 2 } };
      if (path.endsWith("/stages")) return { job_id: "job-1", stages: [], event_count: 0, degraded: false };
      return { job_id: "job-1", findings: [], count: 0, degraded: false };
    }) as typeof apiGet);
    render(<JobDetail jobId="job-1" />);
    await screen.findByText("发现需要处理的问题");
    expect(screen.getByText("受阻")).toBeTruthy();
    expect(screen.queryByText("BLOCKED")).toBeNull();
  });

  it("offers a next-step action that jumps to the risks when blocked with findings", async () => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/job-1") return { job: { id: "job-1", status: "BLOCKED" } };
      if (path.endsWith("/summary")) return { summary: { verdict: "BLOCKED", contracts_total: 4, matrix_failed: 2 } };
      if (path.endsWith("/stages")) return { job_id: "job-1", stages: [], event_count: 0, degraded: false };
      return { job_id: "job-1", findings: [{ id: "f-1", severity: "BLOCKER", evidence_type: "runtime_test", contract_id: "AUTH-01", description: "权限检查被移除" }], count: 3, degraded: false };
    }) as typeof apiGet);
    render(<JobDetail jobId="job-1" />);
    const cta = await screen.findByRole("button", { name: /查看 3 条风险并处理/ });
    expect(screen.getByText("验证结论")).toBeTruthy();
    fireEvent.click(cta);
    await waitFor(() => expect(screen.queryByText("验证结论")).toBeNull());
    // landed on the risks tab: localized table headers + a plain-Chinese evidence gloss
    expect(await screen.findByText("严重程度")).toBeTruthy();
    expect(screen.queryByText("Severity")).toBeNull();
    expect(screen.getAllByText(/运行时测试/).length).toBeGreaterThan(0);
  });

  it("explains an unresolvable git ref in Chinese instead of the raw git stderr", async () => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/job-1") return { job: { id: "job-1", status: "FAILED" } };
      if (path.endsWith("/summary")) return { summary: { verdict: "FAILED", errors: ["Repository safety check failed for base prepare (ref_in_repo: ref 'feature-x' does not belong to the repository: fatal: unknown revision or path not in the working tree.); worktree not created"] } };
      if (path.endsWith("/stages")) return { job_id: "job-1", stages: [], event_count: 0, degraded: false };
      return { job_id: "job-1", findings: [], count: 0, degraded: false };
    }) as typeof apiGet);
    render(<JobDetail jobId="job-1" />);
    await screen.findByText(/版本引用无法解析/);
    expect(screen.getByText(/分支名、标签或完整的提交 SHA/)).toBeTruthy();
    expect(screen.queryByText(/does not belong to the repository/)).toBeNull();
    expect(document.querySelector(".errorbox")?.getAttribute("title")).toMatch(/unknown revision/);
  });

  it("explains a demo-only counterexample gap in Chinese instead of the raw English", async () => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/job-1") return { job: { id: "job-1", status: "UNVERIFIED" } };
      if (path.endsWith("/summary")) return { summary: { verdict: "UNVERIFIED", contracts_total: 3, matrix_unverified: 3, errors: ["Deterministic template only supports the demo repository (com.specproof); LLM generation also failed. No counterexample test produced."] } };
      if (path.endsWith("/stages")) return { job_id: "job-1", stages: [], event_count: 0, degraded: false };
      return { job_id: "job-1", findings: [], count: 0, degraded: false };
    }) as typeof apiGet);
    render(<JobDetail jobId="job-1" />);
    await screen.findByText(/演示仓库/);
    expect(screen.getByText(/接入对应检查器后重新验证/)).toBeTruthy();
    expect(screen.queryByText(/Deterministic template only supports/)).toBeNull();
    // raw string is preserved for hover/audit without leaking as visible text
    expect(document.querySelector(".errorbox")?.getAttribute("title")).toMatch(/Deterministic template/);
  });

  it("shows the environment preflight result with a Chinese next step", async () => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/preflight-job") return { job: { id: "preflight-job", status: "FAILED", repo_path: "/repo" } };
      if (path.endsWith("/summary")) return {
        summary: {
          verdict: "FAILED",
          errors: ["Preflight: Java not found. Install Eclipse Temurin JDK 21 from https://adoptium.net/."],
          preflight: {
            passed: false,
            language: "java",
            checks: [
              { check: "disk_space", status: "PASS", detail: "38.8 GB" },
              { check: "java", status: "FAIL", detail: "Not found" },
            ],
            warnings: ["JAVA_HOME is not set."],
            skipped: ["node", "package_manager"],
          },
        },
      };
      if (path.endsWith("/stages")) return { job_id: "preflight-job", stages: [], event_count: 0, degraded: false };
      return { job_id: "preflight-job", findings: [], count: 0, degraded: false };
    }) as typeof apiGet);
    render(<JobDetail jobId="preflight-job" />);
    await screen.findByText("执行环境预检");
    expect(screen.getByText("环境不满足")).toBeTruthy();
    expect(screen.getByText("Java / Maven")).toBeTruthy();
    // check ids are translated, not leaked as raw English
    expect(screen.getByText("磁盘空间")).toBeTruthy();
    expect(screen.getByText("Java 运行时")).toBeTruthy();
    expect(screen.queryByText("maven_wrapper")).toBeNull();
    // blocking reason becomes an actionable Chinese card, raw string on hover
    expect(screen.getByText(/安装 Eclipse Temurin JDK 21/)).toBeTruthy();
    expect(screen.queryByText(/^Preflight: Java not found/)).toBeNull();
    expect(document.querySelector(".errorbox")?.getAttribute("title")).toMatch(/Java not found/);
  });

  it("hides the preflight card when nothing was recorded", async () => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/plain-job") return { job: { id: "plain-job", status: "VERIFIED" } };
      if (path.endsWith("/summary")) return { summary: { verdict: "VERIFIED", matrix_passed: 2 } };
      if (path.endsWith("/stages")) return { job_id: "plain-job", stages: [], event_count: 0, degraded: false };
      return { job_id: "plain-job", findings: [], count: 0, degraded: false };
    }) as typeof apiGet);
    render(<JobDetail jobId="plain-job" />);
    await screen.findByText("本次验证通过");
    expect(screen.queryByText("执行环境预检")).toBeNull();
  });

  it("does not claim a clean risk scan when the findings read failed", async () => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/job-1") return { job: { id: "job-1", status: "VERIFIED", repo_path: "/project" } };
      if (path.endsWith("/summary")) return { summary: { verdict: "VERIFIED", matrix_passed: 2 } };
      if (path.endsWith("/stages")) return { job_id: "job-1", stages: [], event_count: 0, degraded: false };
      if (path.endsWith("/findings")) throw new Error("findings service unavailable");
      return { job_id: "job-1", findings: [], count: 0, degraded: false };
    }) as typeof apiGet);
    render(<JobDetail jobId="job-1" />);
    await screen.findByText("本次验证通过");
    fireEvent.click(screen.getByRole("tab", { name: /风险发现/ }));
    await waitFor(() => expect(screen.getByText(/无法确认是否存在风险/)).toBeTruthy());
    // the honest failure must replace the reassuring "no findings" empty state
    expect(screen.queryByText(/暂未发现已确认的问题/)).toBeNull();
  });

  it("glosses the verification depth enum while keeping the raw token visible", async () => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/job-1") return { job: { id: "job-1", status: "VERIFIED", depth: "STANDARD", repo_path: "/p" } };
      if (path.endsWith("/summary")) return { summary: { verdict: "VERIFIED", matrix_passed: 2 } };
      if (path.endsWith("/stages")) return { job_id: "job-1", stages: [], event_count: 0, degraded: false };
      return { job_id: "job-1", findings: [], count: 0, degraded: false };
    }) as typeof apiGet);
    render(<JobDetail jobId="job-1" />);
    await screen.findByText("本次验证通过");
    expect(screen.getByText(/标准验证 · STANDARD/)).toBeTruthy();
  });

  it("passes an unknown verification depth through verbatim", async () => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/job-1") return { job: { id: "job-1", status: "VERIFIED", depth: "PARANOID", repo_path: "/p" } };
      if (path.endsWith("/summary")) return { summary: { verdict: "VERIFIED", matrix_passed: 2 } };
      if (path.endsWith("/stages")) return { job_id: "job-1", stages: [], event_count: 0, degraded: false };
      return { job_id: "job-1", findings: [], count: 0, degraded: false };
    }) as typeof apiGet);
    render(<JobDetail jobId="job-1" />);
    await screen.findByText("本次验证通过");
    expect(screen.getByText("PARANOID")).toBeTruthy();
  });

  it("loads the report only when requested", async () => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/job-1") return { job: { id: "job-1", status: "VERIFIED" } };
      if (path.endsWith("/summary")) return { summary: {} };
      if (path.endsWith("/stages")) return { job_id: "job-1", stages: [], event_count: 0, degraded: false };
      if (path.endsWith("/certificate")) return { path: "report.json", document: { verdict: "VERIFIED" } };
      return { job_id: "job-1", findings: [], count: 0, degraded: false };
    }) as typeof apiGet);
    render(<JobDetail jobId="job-1" />);
    await screen.findByText("本次验证通过");
    expect(get.mock.calls.some(([path]) => path.endsWith("/certificate"))).toBe(false);
    fireEvent.click(screen.getByRole("tab", { name: "验证报告" }));
    await waitFor(() => expect(get.mock.calls.some(([path]) => path.endsWith("/certificate"))).toBe(true));
  });
});

describe("overview with no summary (#62) — why it is missing must be the status", () => {
  // One empty state used to cover every "no summary" case and it promised
  // "执行完成后，这里会展示…", i.e. it told a reader to wait for something that
  // is never coming when the row is already terminal. Terminal here follows
  // the backend's own set (storage/mysql.py TERMINAL_STATUSES), where FAILED
  // is deliberately NOT terminal — it stays retryable.
  const stub = async (status: string) => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/job-1") return { job: { id: "job-1", status, repo_path: "/project" } };
      if (path.endsWith("/summary")) return { summary: {} };
      if (path.endsWith("/stages")) return { job_id: "job-1", stages: [], event_count: 0, degraded: false };
      return { job_id: "job-1", findings: [], count: 0, degraded: false };
    }) as typeof apiGet);
    render(<JobDetail jobId="job-1" />);
    await screen.findByRole("tablist");
  };

  it("still running: says it is running, and never claims a missing record", async () => {
    await stub("RUNNING");
    expect(screen.getByText("验证仍在执行中，完成后这里会展示结论、需求覆盖与风险证据。")).toBeTruthy();
    expect(screen.queryByText(/不会随刷新补/)).toBeNull();
    expect(screen.queryByText("这一轮以执行失败结束，记录里没有验证摘要。")).toBeNull();
  });

  it("FAILED: does not promise a summary on refresh", async () => {
    await stub("FAILED");
    expect(screen.getByText("这一轮以执行失败结束，记录里没有验证摘要。")).toBeTruthy();
    expect(screen.queryByText("验证仍在执行中，完成后这里会展示结论、需求覆盖与风险证据。")).toBeNull();
    expect(screen.queryByText(/执行完成后，这里会展示/)).toBeNull();
  });

  it("terminal without a summary: says the record will not arrive", async () => {
    await stub("VERIFIED");
    expect(screen.getByText("任务已进入终态，但记录里没有验证摘要。")).toBeTruthy();
    expect(screen.getByText(/不会随刷新补上/)).toBeTruthy();
    expect(screen.queryByText(/执行完成后，这里会展示/)).toBeNull();
  });

  it("an unrecognised status passes through instead of being called terminal", async () => {
    await stub("SOMETHING_NEW");
    expect(screen.getByText(/这是本页面未识别的状态/)).toBeTruthy();
    expect(screen.getByText(/任务状态为 SOMETHING_NEW/)).toBeTruthy();
    expect(screen.getByText(/既不等于已终态，也不等于仍在执行/)).toBeTruthy();
    expect(screen.queryByText("任务已进入终态，但记录里没有验证摘要。")).toBeNull();
  });
});

