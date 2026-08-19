/**
 * Unit tests for the pure API client layer (src/client.ts).
 * Runs on plain Node with an injected fetch — no VS Code host involved.
 */

import { describe, expect, it } from "vitest";
import {
  AgentApiClient,
  AgentApiError,
  describeAgentError,
  firstActiveJob,
  isTerminalStatus,
  type AgentJobSummary,
} from "../src/client";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

interface RecordedCall {
  url: string;
  init: RequestInit | undefined;
}

function recordingFetch(responder: (call: RecordedCall) => Response) {
  const calls: RecordedCall[] = [];
  const fn = async (
    input: string | URL | Request,
    init?: RequestInit,
  ): Promise<Response> => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;
    const call: RecordedCall = { url, init };
    calls.push(call);
    return responder(call);
  };
  return { calls, fn: fn as typeof fetch };
}

function summary(status: AgentJobSummary["status"]): AgentJobSummary {
  return {
    id: "job-1",
    task_name: "demo-task",
    repo_path: "D:/experim/repo",
    status,
    plan_steps: 2,
    events_count: 4,
    approvals_count: 0,
    created_at: "2026-08-18T00:00:00+00:00",
    updated_at: "2026-08-18T00:01:00+00:00",
  };
}

describe("AgentApiClient.listJobs", () => {
  it("requests GET /agent/jobs with the API key and parses the list envelope", async () => {
    const body = { jobs: [summary("PLANNING")], count: 1, filter: { status: null } };
    const recorder = recordingFetch(() => json(body));
    const client = new AgentApiClient({ apiKey: "replace_me", fetchFn: recorder.fn });

    const result = await client.listJobs();

    expect(result.count).toBe(1);
    expect(result.jobs[0].status).toBe("PLANNING");
    const call = recorder.calls[0];
    expect(call.url).toBe("http://127.0.0.1:8000/agent/jobs");
    expect(call.init?.method).toBe("GET");
    expect((call.init?.headers as Record<string, string>)["X-API-Key"]).toBe("replace_me");
  });

  it("appends the status filter query parameter", async () => {
    const recorder = recordingFetch(() => json({ jobs: [], count: 0, filter: { status: "EXECUTING" } }));
    const client = new AgentApiClient({ fetchFn: recorder.fn });

    await client.listJobs("EXECUTING");

    expect(recorder.calls[0].url).toBe("http://127.0.0.1:8000/agent/jobs?status=EXECUTING");
  });

  it("omits the X-API-Key header when no key is configured", async () => {
    const recorder = recordingFetch(() => json({ jobs: [], count: 0, filter: { status: null } }));
    const client = new AgentApiClient({ fetchFn: recorder.fn });

    await client.listJobs();

    const headers = recorder.calls[0].init?.headers as Record<string, string>;
    expect(headers["X-API-Key"]).toBeUndefined();
    expect(headers["Content-Type"]).toBe("application/json");
  });
});

describe("AgentApiClient.getJob", () => {
  it("requests GET /agent/jobs/{id} and returns the job envelope", async () => {
    const job = { id: "job-1", status: "AWAITING_APPROVAL", plan: { version: 1, steps: [] }, progress: { percent: 50, message: "planned", updated_at: "2026-08-18T00:01:00+00:00" }, result: null };
    const recorder = recordingFetch(() => json({ job }));
    const client = new AgentApiClient({ fetchFn: recorder.fn });

    const result = await client.getJob("job-1");

    expect(result.job.status).toBe("AWAITING_APPROVAL");
    expect(recorder.calls[0].url).toBe("http://127.0.0.1:8000/agent/jobs/job-1");
  });

  it("percent-encodes the job id in the path", async () => {
    const recorder = recordingFetch(() => json({ job: {} }));
    const client = new AgentApiClient({ fetchFn: recorder.fn });

    await client.getJob("a/b");

    expect(recorder.calls[0].url).toBe("http://127.0.0.1:8000/agent/jobs/a%2Fb");
  });
});

describe("AgentApiClient.createJob", () => {
  it("posts repo_path/spec_text/auto_start in snake_case and returns the 202 shape", async () => {
    const recorder = recordingFetch(() => json({ job_id: "job-9", status: "PLANNING" }, 202));
    const client = new AgentApiClient({ fetchFn: recorder.fn });

    const result = await client.createJob({
      repoPath: "D:/experim/repo",
      specText: "Add pagination",
      taskName: "job-9",
    });

    expect(result.job_id).toBe("job-9");
    expect(result.status).toBe("PLANNING");
    expect(recorder.calls[0].url).toBe("http://127.0.0.1:8000/agent/jobs");
    expect(recorder.calls[0].init?.method).toBe("POST");
    expect(JSON.parse(recorder.calls[0].init?.body as string)).toEqual({
      repo_path: "D:/experim/repo",
      spec_text: "Add pagination",
      auto_start: false,
      task_name: "job-9",
    });
  });

  it("omits task_name from the body when not provided", async () => {
    const recorder = recordingFetch(() => json({ job_id: "job-9", status: "PLANNING" }, 202));
    const client = new AgentApiClient({ fetchFn: recorder.fn });

    await client.createJob({ repoPath: "D:/experim/repo", specText: "Add pagination" });

    const body = JSON.parse(recorder.calls[0].init?.body as string);
    expect(body).not.toHaveProperty("task_name");
    expect(body.auto_start).toBe(false);
  });

  it("forwards autoStart as auto_start", async () => {
    const recorder = recordingFetch(() => json({ job_id: "job-9", status: "PLANNING" }, 202));
    const client = new AgentApiClient({ fetchFn: recorder.fn });

    await client.createJob({ repoPath: "", specText: "", autoStart: true });

    const body = JSON.parse(recorder.calls[0].init?.body as string);
    expect(body.auto_start).toBe(true);
  });
});

describe("AgentApiClient.cancelJob", () => {
  it("posts the cancel route and returns the 202 shape", async () => {
    const recorder = recordingFetch(() => json({ job_id: "job-1", status: "CANCELLED" }, 202));
    const client = new AgentApiClient({ fetchFn: recorder.fn });

    const result = await client.cancelJob("job-1");

    expect(result.status).toBe("CANCELLED");
    expect(recorder.calls[0].url).toBe("http://127.0.0.1:8000/agent/jobs/job-1/cancel");
    expect(recorder.calls[0].init?.method).toBe("POST");
  });
});

describe("AgentApiClient.approveJob", () => {
  it("defaults target to plan and sends the decision", async () => {
    const recorder = recordingFetch(() =>
      json({ approval: { id: "a1", job_id: "job-1", target: "plan", step_index: null, decision: "approve", note: null, actor: "console", created_at: "2026-08-18T00:02:00+00:00" }, job: { id: "job-1", status: "EXECUTING" } }),
    );
    const client = new AgentApiClient({ fetchFn: recorder.fn });

    const result = await client.approveJob("job-1", { decision: "approve" });

    expect(result.job.status).toBe("EXECUTING");
    expect(recorder.calls[0].url).toBe("http://127.0.0.1:8000/agent/jobs/job-1/approve");
    expect(JSON.parse(recorder.calls[0].init?.body as string)).toEqual({
      decision: "approve",
      target: "plan",
    });
  });

  it("sends note and step_index for a step decision", async () => {
    const recorder = recordingFetch(() =>
      json({ approval: { id: "a2", job_id: "job-1", target: "step", step_index: 1, decision: "reject", note: "wrong file", actor: "console", created_at: "2026-08-18T00:02:00+00:00" }, job: { id: "job-1", status: "FAILED" } }),
    );
    const client = new AgentApiClient({ fetchFn: recorder.fn });

    await client.approveJob("job-1", {
      decision: "reject",
      target: "step",
      stepIndex: 1,
      note: "wrong file",
    });

    expect(JSON.parse(recorder.calls[0].init?.body as string)).toEqual({
      decision: "reject",
      target: "step",
      note: "wrong file",
      step_index: 1,
    });
  });
});

describe("AgentApiClient.getDiff", () => {
  it("returns the structured diff response", async () => {
    const diffBody = {
      job_id: "job-1",
      mode: "unified",
      stats: { files_changed: 1, insertions: 1, deletions: 1 },
      files: [
        {
          path: "src/calc.py",
          status: "modified",
          hunks: [
            {
              old_start: 1, old_count: 1, new_start: 1, new_count: 1,
              lines: [
                { type: "del", old_no: 1, new_no: null, text: "x = 1" },
                { type: "add", old_no: null, new_no: 1, text: "x = 2" },
              ],
            },
          ],
          insertions: 1,
          deletions: 1,
        },
      ],
      generated_at: "2026-08-18T00:03:00+00:00",
    };
    const recorder = recordingFetch(() => json(diffBody));
    const client = new AgentApiClient({ fetchFn: recorder.fn });

    const result = await client.getDiff("job-1");

    expect(result.stats.files_changed).toBe(1);
    expect(result.files[0].hunks[0].lines[0].type).toBe("del");
    expect(recorder.calls[0].url).toBe("http://127.0.0.1:8000/agent/jobs/job-1/diff");
  });
});

describe("AgentApiClient error handling", () => {
  it("throws AgentApiError with the §8.1 envelope fields on 404", async () => {
    const envelope = {
      detail: "Agent job nope not found",
      error: {
        code: "JOB_NOT_FOUND",
        message: "Agent job nope not found",
        request_id: "3fa0c2e19b4d4a1f",
      },
      schema_version: 1,
    };
    const recorder = recordingFetch(() => json(envelope, 404));
    const client = new AgentApiClient({ fetchFn: recorder.fn });

    const error = await client.getJob("nope").then(
      () => null,
      (caught: unknown) => caught as AgentApiError,
    );

    expect(error).toBeInstanceOf(AgentApiError);
    expect(error?.status).toBe(404);
    expect(error?.code).toBe("JOB_NOT_FOUND");
    expect(error?.requestId).toBe("3fa0c2e19b4d4a1f");
    expect(error?.message).toBe("Agent job nope not found");
  });

  it("survives non-JSON error bodies with code UNKNOWN and the raw body as message", async () => {
    const recorder = recordingFetch(() => new Response("gateway boom", { status: 502 }));
    const client = new AgentApiClient({ fetchFn: recorder.fn });

    const error = await client.listJobs().then(
      () => null,
      (caught: unknown) => caught as AgentApiError,
    );

    expect(error?.status).toBe(502);
    expect(error?.code).toBe("UNKNOWN");
    expect(error?.message).toBe("gateway boom");
  });

  it("falls back to a status message for empty error bodies", async () => {
    const recorder = recordingFetch(() => new Response("", { status: 500 }));
    const client = new AgentApiClient({ fetchFn: recorder.fn });

    const error = await client.listJobs().then(
      () => null,
      (caught: unknown) => caught as AgentApiError,
    );

    expect(error?.message).toBe("Agent API request failed with status 500");
  });
});

describe("AgentApiClient base URL handling", () => {
  it("strips trailing slashes so paths join with a single slash", async () => {
    const recorder = recordingFetch(() => json({ jobs: [], count: 0, filter: { status: null } }));
    const client = new AgentApiClient({ baseUrl: "http://127.0.0.1:8000///", fetchFn: recorder.fn });

    await client.listJobs();

    expect(recorder.calls[0].url).toBe("http://127.0.0.1:8000/agent/jobs");
  });

  it("uses the configured base URL", async () => {
    const recorder = recordingFetch(() => json({ jobs: [], count: 0, filter: { status: null } }));
    const client = new AgentApiClient({ baseUrl: "http://localhost:9000", fetchFn: recorder.fn });

    await client.listJobs();

    expect(recorder.calls[0].url).toBe("http://localhost:9000/agent/jobs");
  });
});

describe("describeAgentError", () => {
  it("formats AgentApiError with code and request id", () => {
    const error = new AgentApiError(
      409,
      { error: { code: "STATE_CONFLICT", message: "terminal job", request_id: "abc1" } },
      "{}",
    );
    expect(describeAgentError(error)).toBe("[STATE_CONFLICT] terminal job (request abc1)");
  });

  it("falls back to plain messages for other errors", () => {
    expect(describeAgentError(new Error("boom"))).toBe("boom");
    expect(describeAgentError("nope")).toBe("nope");
  });
});

describe("status helpers", () => {
  it("classifies terminal and active statuses", () => {
    expect(isTerminalStatus("COMPLETED")).toBe(true);
    expect(isTerminalStatus("FAILED")).toBe(true);
    expect(isTerminalStatus("CANCELLED")).toBe(true);
    expect(isTerminalStatus("EXECUTING")).toBe(false);
    expect(isTerminalStatus("PLANNING")).toBe(false);
    expect(isTerminalStatus("AWAITING_APPROVAL")).toBe(false);
  });

  it("picks the first active job from a list", () => {
    const jobs = [
      summary("COMPLETED"),
      summary("EXECUTING"),
      summary("PLANNING"),
    ];
    expect(firstActiveJob(jobs)?.status).toBe("EXECUTING");
    expect(firstActiveJob([summary("COMPLETED"), summary("CANCELLED")])).toBeUndefined();
  });
});
