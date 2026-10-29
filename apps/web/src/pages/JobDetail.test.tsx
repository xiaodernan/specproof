import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import JobDetail from "./JobDetail";
import { apiGet, openProgressStream } from "../api";

vi.mock("../api", () => ({
  apiGet: vi.fn(),
  openProgressStream: vi.fn(),
  downloadCapsule: vi.fn(),
  // SameRepoCraftPanel reads the agent list on every job detail view.
  listAgentJobs: vi.fn().mockResolvedValue({ jobs: [], count: 0, filter: { status: null } }),
}));
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
      return { job_id: "job-1", findings: [{ id: "f-1", severity: "BLOCKER", evidence_type: "java_source_diff", contract_id: "AUTH-01", description: "权限检查被移除" }], count: 3, degraded: false };
    }) as typeof apiGet);
    render(<JobDetail jobId="job-1" />);
    const cta = await screen.findByRole("button", { name: /查看 3 条风险并处理/ });
    expect(screen.getByText("验证结论")).toBeTruthy();
    fireEvent.click(cta);
    await waitFor(() => expect(screen.queryByText("验证结论")).toBeNull());
    // landed on the risks tab: localized table headers + a plain-Chinese evidence gloss
    expect(await screen.findByText("严重程度")).toBeTruthy();
    expect(screen.queryByText("Severity")).toBeNull();
    expect(screen.getAllByText(/Java 源码差分/).length).toBeGreaterThan(0);
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
      // A real job status: RUNNING never transitions to UNVERIFIED (that is a
      // verdict word), so the old fixture was certifying an unreachable state.
      if (path === "/jobs/job-1") return { job: { id: "job-1", status: "BLOCKED" } };
      if (path.endsWith("/summary")) return { summary: { verdict: "BLOCKED", contracts_total: 3, matrix_unverified: 3, errors: ["Deterministic template only supports the demo repository (com.specproof); LLM generation also failed. No counterexample test produced."] } };
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

  it("does not call a skipped preflight 环境正常 on the job page (#191)", async () => {
    // Same #190 reading rule, one level up: a VERIFIED job can carry
    // preflight.passed=true with not_run=probe_error — passed is true because
    // the failure was swallowed fail-open, not because anything was checked.
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/probe-skipped-job") return { job: { id: "probe-skipped-job", status: "VERIFIED", repo_path: "/repo" } };
      if (path.endsWith("/summary")) return {
        summary: {
          verdict: "VERIFIED",
          preflight: { passed: true, not_run: "probe_error" },
        },
      };
      if (path.endsWith("/stages")) return { job_id: "probe-skipped-job", stages: [], event_count: 0, degraded: false };
      return { job_id: "probe-skipped-job", findings: [], count: 0, degraded: false };
    }) as typeof apiGet);
    render(<JobDetail jobId="probe-skipped-job" />);
    await screen.findByText("执行环境预检");
    expect(screen.getByText("环境未验证")).toBeTruthy();
    expect(screen.getByText("环境探测自身异常，已跳过预检并继续验证。")).toBeTruthy();
    expect(screen.queryByText("环境正常")).toBeNull();
    expect(screen.queryByText("环境不满足")).toBeNull();
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

  it("discloses DEEP verification results when the summary carries them", async () => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/deep-job") return { job: { id: "deep-job", status: "VERIFIED", depth: "DEEP", repo_path: "/p" } };
      if (path.endsWith("/summary")) return {
        summary: {
          verdict: "VERIFIED",
          deep_note: "DEEP experiments completed: mutation campaigns=2, state delta captured",
          deep_results: {
            verdict_stability: { repeat_count: 2, verdicts: ["exit_0", "exit_0"], classification: "stable" },
            cache_integrity: "cache seeded from the sandbox note",
            deep_report_file: "deep-report-deep-job.json",
          },
        },
      };
      if (path.endsWith("/stages")) return { job_id: "deep-job", stages: [], event_count: 0, degraded: false };
      return { job_id: "deep-job", findings: [], count: 0, degraded: false };
    }) as typeof apiGet);
    render(<JobDetail jobId="deep-job" />);
    await screen.findByText("DEEP 深度验证披露");
    // classification is glossed, the raw enum token stays visible
    expect(screen.getByText(/结论稳定 · stable/)).toBeTruthy();
    expect(screen.getByText(/2 次重复运行/)).toBeTruthy();
    // the run-produced note is shown verbatim, never paraphrased
    expect(screen.getByText(/mutation campaigns=2/)).toBeTruthy();
    expect(screen.getByText("deep-report-deep-job.json")).toBeTruthy();
  });

  it("renders no DEEP disclosure panel when the tier produced nothing", async () => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/fast-job") return { job: { id: "fast-job", status: "VERIFIED", depth: "FAST", repo_path: "/p" } };
      if (path.endsWith("/summary")) return { summary: { verdict: "VERIFIED", matrix_passed: 2, deep_note: "DEEP tier not requested" } };
      if (path.endsWith("/stages")) return { job_id: "fast-job", stages: [], event_count: 0, degraded: false };
      return { job_id: "fast-job", findings: [], count: 0, degraded: false };
    }) as typeof apiGet);
    render(<JobDetail jobId="fast-job" />);
    await screen.findByText("本次验证通过");
    expect(screen.queryByText("DEEP 深度验证披露")).toBeNull();
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

describe("coverage_reason disclosure (#169) — the banner may only claim what the payload proves", () => {
  // Measured before this block was written:
  //   * evidence/verdict.py::evaluate_verification emits a reason per cause family —
  //     零检查 / 记录格式无效 / 缺少契约检查结果 / 没有对应验收契约 / 汇总不一致 /
  //     「存在 N 项已确认问题」 / 「执行过程有错误」 — and release_gate_veto adds the
  //     「RELEASE 档发布门 …」 refusals; VerificationDecision.reason joins them with 「；」.
  //   * agent/worker.py::_state_summary persists that joined string as `coverage_reason`
  //     next to `matrix_rows_total` (from _matrix_rows_for_summary), and
  //     api/routes/jobs.py::get_job_summary hands the summary through unfiltered.
  // So `matrix_rows_total === 0` is the only reading that proves「本次没有形成可执行的
  // 检查项」, while the previous copy asserted that sentence — and the 补全指引 route —
  // for every reason at all.
  // Predicted red set against the previous JobDetail.tsx: cases 1, 3 and 4 RED,
  // case 2 GREEN (it is the one case where the old sentence was true).
  const stub = async (
    summary: Record<string, unknown>,
    findings: Record<string, unknown> = { findings: [], count: 0, degraded: false },
  ) => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/job-1") return { job: { id: "job-1", status: "BLOCKED", repo_path: "/project" } };
      if (path.endsWith("/summary")) return { summary };
      if (path.endsWith("/stages")) return { job_id: "job-1", stages: [], event_count: 0, degraded: false };
      return { job_id: "job-1", ...findings };
    }) as typeof apiGet);
    render(<JobDetail jobId="job-1" />);
    await screen.findByRole("tablist");
  };

  it("names a RELEASE gate refusal without claiming there were no checks", async () => {
    await stub({
      verdict: "BLOCKED", contracts_total: 4, matrix_rows_total: 4, matrix_unverified: 1,
      coverage_reason: "RELEASE 档发布门 verified_release_gates: 未通过",
    });
    // the reason still reaches the reader verbatim (#150 disclosure stays)
    expect(screen.getByText(/RELEASE 档发布门 verified_release_gates: 未通过/)).toBeTruthy();
    // and the page must not describe four executed checks as「没有形成可执行的检查项」
    expect(screen.queryByText(/本次没有形成可执行的检查项/)).toBeNull();
    expect(screen.getByText("本次不能确认验收通过")).toBeTruthy();
    expect(screen.getByText(/已形成 4 项检查/)).toBeTruthy();
    // a job that did compile checks is not sent to the onboarding guide
    expect(screen.queryByRole("link", { name: /了解支持的验收方式/ })).toBeNull();
    expect(screen.getByRole("link", { name: /逐项查看未确认的验收条件/ })).toBeTruthy();
    // added after the measured run above, so its old-code red is read from HEAD's
    // `<strong>验收覆盖不足</strong>` rather than re-measured; arm L1 re-proves it
    expect(screen.getByText("本次验收结论未能确认")).toBeTruthy();
  });

  it("keeps the zero-check copy when the payload really records zero rows", async () => {
    await stub({
      verdict: "BLOCKED", contracts_total: 0, matrix_rows_total: 0,
      coverage_reason: "零检查不能判定验收通过：请补充验收条件并接入适用检查器",
    });
    expect(screen.getByText("覆盖不足，暂不能确认验收通过")).toBeTruthy();
    expect(screen.getByText(/本次没有形成可执行的检查项/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /了解支持的验收方式/ })).toBeTruthy();
    expect(screen.queryByText(/已形成/)).toBeNull();
  });

  it("an absent matrix_rows_total is not read as zero checks", async () => {
    // Summaries persisted before 2026-09-23 carry no row count. Absence must not
    // become 0, or the page invents the very claim this unit is removing.
    await stub({ verdict: "BLOCKED", contracts_total: 3, coverage_reason: "缺少契约检查结果：AUTH-03" });
    expect(screen.queryByText(/本次没有形成可执行的检查项/)).toBeNull();
    expect(screen.getByText("本次不能确认验收通过")).toBeTruthy();
    expect(screen.queryByText(/已形成/)).toBeNull();
    expect(screen.getByText(/请查看上方原因/)).toBeTruthy();
  });

  it("routes the next step by the payload instead of by any reason at all", async () => {
    await stub({
      verdict: "BLOCKED", contracts_total: 4, matrix_rows_total: 4, matrix_failed: 1,
      coverage_reason: "第 2 条检查失败",
    });
    expect(screen.queryByRole("button", { name: /了解如何补全验证/ })).toBeNull();
    expect(screen.getByRole("button", { name: /逐项查看未确认的验收条件/ })).toBeTruthy();
  });
});

describe("demo badge on the detail page (#526)", () => {
  // The list pages wore the demo badge; the detail page could not, because only
  // the two window reads published is_demo. One record, two truths about it --
  // and the surface a reader slows down on was the unlabeled one.
  const render_job = async (is_demo: number | boolean) => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/badge-job") {
        return { job: { id: "badge-job", status: "BLOCKED", repo_path: "/project", is_demo } };
      }
      throw new Error("Artifacts unavailable");
    }) as typeof apiGet);
    render(<JobDetail jobId="badge-job" />);
    await waitFor(() => expect(document.querySelector(".page-head h1")).not.toBeNull());
  };

  it("labels a seeded verification where the verdict is spelled out", async () => {
    await render_job(1);
    const badge = document.querySelector(".page-head h1 .demo-label");
    expect(badge).not.toBeNull();
    expect((badge?.textContent || "").trim().length).toBeGreaterThan(0);
  });

  it("draws no badge for a real verification, and no bare zero either", async () => {
    // is_demo is 0, not false, and `{job.is_demo && <span/>}` evaluates to 0 --
    // which React renders as the character "0". The !! that used to hide this
    // also hid the missing column, so the page now uses a ternary and this case
    // is what keeps the two from being confused again.
    await render_job(0);
    expect(document.querySelector(".page-head h1 .demo-label")).toBeNull();
    const head = document.querySelector(".page-head h1");
    expect(head?.textContent || "").not.toContain("0");
  });
});
