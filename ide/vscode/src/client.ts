/**
 * Pure HTTP client for the SpecProof agent console API (/agent/jobs).
 *
 * This module deliberately imports nothing from the "vscode" package so it
 * can be unit-tested with vitest on plain Node. The fetch implementation is
 * injectable (AgentApiClientOptions.fetchFn) for deterministic tests.
 *
 * The wire contract mirrors api/routes/agent_console.py:
 *   - auth: X-API-Key header (SPECPROOF_API_KEY server-side)
 *   - POST /agent/jobs                     create (202 -> {job_id, status})
 *   - GET  /agent/jobs[?status=]           list (200 -> {jobs, count, filter})
 *   - GET  /agent/jobs/{id}                detail (200 -> {job})
 *   - POST /agent/jobs/{id}/cancel         cancel (202 -> {job_id, status})
 *   - POST /agent/jobs/{id}/approve        decision (decision/target/note/step_index)
 *   - GET  /agent/jobs/{id}/diff           structured change-bundle diff
 *   - errors: {detail, error: {code, message, request_id}, schema_version}
 */

export type AgentJobStatus =
  | "PLANNING"
  | "AWAITING_APPROVAL"
  | "EXECUTING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export type ApprovalDecision = "approve" | "reject";
export type ApprovalTarget = "plan" | "step" | "gate";

/** GET /agent/jobs entry (summary view). */
export interface AgentJobSummary {
  id: string;
  task_name: string;
  repo_path: string;
  status: AgentJobStatus;
  plan_steps: number;
  events_count: number;
  approvals_count: number;
  created_at: string;
  updated_at: string;
}

export interface AgentJobListResponse {
  jobs: AgentJobSummary[];
  count: number;
  filter: { status: string | null };
}

/** GET /agent/jobs/{id} entry (full view). */
export interface AgentJobDetail {
  id: string;
  task_name: string;
  repo_path: string;
  spec_text: string;
  status: AgentJobStatus;
  plan: unknown | null;
  progress: { percent: number; message: string; updated_at: string };
  result: unknown | null;
  worker_id: string | null;
  created_at: string;
  updated_at: string;
  events_count: number;
  approvals_count: number;
}

export interface AgentJobDetailResponse {
  job: AgentJobDetail;
}

export interface CreateJobRequest {
  repoPath: string;
  specText: string;
  taskName?: string;
  autoStart?: boolean;
}

export interface CreateJobResponse {
  job_id: string;
  status: AgentJobStatus;
}

export interface ApproveRequest {
  decision: ApprovalDecision;
  target?: ApprovalTarget;
  note?: string;
  stepIndex?: number;
}

export interface ApprovalRecord {
  id: string;
  job_id: string;
  target: ApprovalTarget;
  step_index: number | null;
  decision: ApprovalDecision;
  note: string | null;
  actor: string;
  created_at: string;
}

export interface ApprovalResponse {
  approval: ApprovalRecord;
  job: { id: string; status: AgentJobStatus };
}

export type DiffLineType = "add" | "del" | "context";

export interface DiffLine {
  type: DiffLineType;
  old_no: number | null;
  new_no: number | null;
  text: string;
}

export interface DiffHunk {
  old_start: number;
  old_count: number;
  new_start: number;
  new_count: number;
  lines: DiffLine[];
}

export interface DiffFile {
  path: string;
  status: string;
  hunks: DiffHunk[];
  insertions: number;
  deletions: number;
}

export interface DiffResponse {
  job_id: string;
  mode: string;
  stats: { files_changed: number; insertions: number; deletions: number };
  files: DiffFile[];
  generated_at: string;
}

/** §8.1 error envelope carried by non-2xx responses. */
export interface ApiErrorEnvelope {
  detail?: unknown;
  error?: { code?: string; message?: string; request_id?: string | null };
  schema_version?: number;
}

export class AgentApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;

  constructor(status: number, envelope: ApiErrorEnvelope, rawBody: string) {
    const fallback = `Agent API request failed with status ${status}`;
    const message = envelope.error?.message ??
      (rawBody ? rawBody.slice(0, 240) : fallback);
    super(message);
    this.name = "AgentApiError";
    this.status = status;
    this.code = envelope.error?.code ?? "UNKNOWN";
    this.requestId = envelope.error?.request_id ?? null;
  }
}

/** Human-readable single line for any caught error (safe for UI display). */
export function describeAgentError(error: unknown): string {
  if (error instanceof AgentApiError) {
    const suffix = error.requestId ? ` (request ${error.requestId})` : "";
    return `[${error.code}] ${error.message}${suffix}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

export interface AgentApiClientOptions {
  /** Base URL of the API server, e.g. "http://127.0.0.1:8000". */
  baseUrl?: string;
  /** Value for the X-API-Key header (omitted when empty). */
  apiKey?: string;
  /** Injectable fetch for tests and custom transports. */
  fetchFn?: typeof fetch;
}

export const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export const ALL_AGENT_STATUSES: readonly AgentJobStatus[] = [
  "PLANNING",
  "AWAITING_APPROVAL",
  "EXECUTING",
  "COMPLETED",
  "FAILED",
  "CANCELLED",
];

const TERMINAL_STATUSES: ReadonlySet<string> = new Set([
  "COMPLETED",
  "FAILED",
  "CANCELLED",
]);

/** True for the console statuses that accept no cancel/approve transitions. */
export function isTerminalStatus(status: AgentJobStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

/** The first non-terminal job of a list (undefined when all are terminal). */
export function firstActiveJob(jobs: AgentJobSummary[]): AgentJobSummary | undefined {
  return jobs.find((job) => !isTerminalStatus(job.status));
}

function parseJson(text: string): unknown {
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

export class AgentApiClient {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly fetchFn: typeof fetch;

  constructor(options: AgentApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? DEFAULT_API_BASE_URL).replace(/\/+$/, "");
    this.apiKey = options.apiKey ?? "";
    this.fetchFn = options.fetchFn ?? fetch;
  }

  getBaseUrl(): string {
    return this.baseUrl;
  }

  private buildHeaders(): Record<string, string> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (this.apiKey) {
      headers["X-API-Key"] = this.apiKey;
    }
    return headers;
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const response = await this.fetchFn(`${this.baseUrl}${path}`, {
      method,
      headers: this.buildHeaders(),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const rawBody = await response.text();
    const payload = parseJson(rawBody);
    if (!response.ok) {
      throw new AgentApiError(
        response.status,
        (payload ?? {}) as ApiErrorEnvelope,
        rawBody,
      );
    }
    return payload as T;
  }

  /** GET /agent/jobs with an optional exact console-status filter. */
  listJobs(status?: AgentJobStatus): Promise<AgentJobListResponse> {
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    return this.request<AgentJobListResponse>("GET", `/agent/jobs${query}`);
  }

  /** GET /agent/jobs/{id}. */
  getJob(jobId: string): Promise<AgentJobDetailResponse> {
    return this.request<AgentJobDetailResponse>(
      "GET",
      `/agent/jobs/${encodeURIComponent(jobId)}`,
    );
  }

  /** POST /agent/jobs (202 on success). */
  createJob(input: CreateJobRequest): Promise<CreateJobResponse> {
    const body: Record<string, unknown> = {
      repo_path: input.repoPath,
      spec_text: input.specText,
      auto_start: input.autoStart ?? false,
    };
    if (input.taskName !== undefined) {
      body["task_name"] = input.taskName;
    }
    return this.request<CreateJobResponse>("POST", "/agent/jobs", body);
  }

  /** POST /agent/jobs/{id}/cancel (202 on success). */
  cancelJob(jobId: string): Promise<{ job_id: string; status: AgentJobStatus }> {
    return this.request<{ job_id: string; status: AgentJobStatus }>(
      "POST",
      `/agent/jobs/${encodeURIComponent(jobId)}/cancel`,
    );
  }

  /** POST /agent/jobs/{id}/approve with decision/target/note/step_index. */
  approveJob(jobId: string, input: ApproveRequest): Promise<ApprovalResponse> {
    const body: Record<string, unknown> = {
      decision: input.decision,
      target: input.target ?? "plan",
    };
    if (input.note !== undefined) {
      body["note"] = input.note;
    }
    if (input.stepIndex !== undefined) {
      body["step_index"] = input.stepIndex;
    }
    return this.request<ApprovalResponse>(
      "POST",
      `/agent/jobs/${encodeURIComponent(jobId)}/approve`,
      body,
    );
  }

  /** GET /agent/jobs/{id}/diff — structured change-bundle diff. */
  getDiff(jobId: string): Promise<DiffResponse> {
    return this.request<DiffResponse>(
      "GET",
      `/agent/jobs/${encodeURIComponent(jobId)}/diff`,
    );
  }
}
