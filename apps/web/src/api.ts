// Unified API client: fetch + SSE, explicit errors and degradation states.
// The API key lives in sessionStorage and is sent as X-API-Key (the SSE
// progress stream additionally passes it as a query parameter because
// EventSource cannot set headers).

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

const KEY_STORAGE = "specproof_api_key";
const BASE_STORAGE = "specproof_api_base";

export function apiBase(): string {
  try {
    return window.localStorage.getItem(BASE_STORAGE) || "";
  } catch {
    return "";
  }
}

export function setApiBase(base: string): void {
  try {
    window.localStorage.setItem(BASE_STORAGE, base);
  } catch {
    // storage unavailable; base stays default
  }
}

export function getApiKey(): string {
  try {
    return window.sessionStorage.getItem(KEY_STORAGE) || "";
  } catch {
    return "";
  }
}

export function setApiKey(key: string): void {
  try {
    window.sessionStorage.setItem(KEY_STORAGE, key);
  } catch {
    // storage unavailable; key lives only in memory
  }
}

export function clearApiKey(): void {
  try {
    window.sessionStorage.removeItem(KEY_STORAGE);
  } catch {
    // ignore
  }
}

function headers(): Record<string, string> {
  const h: Record<string, string> = { Accept: "application/json" };
  const key = getApiKey();
  if (key) h["X-API-Key"] = key;
  return h;
}

export async function apiGet<T>(path: string): Promise<T> {
  const resp = await fetch(apiBase() + path, { headers: headers() });
  return handleResponse<T>(resp);
}

async function handleResponse<T>(resp: Response): Promise<T> {
  if (resp.ok) {
    try {
      return (await resp.json()) as T;
    } catch {
      return {} as T;
    }
  }
  let detail = resp.statusText;
  try {
    const body = await resp.json();
    if (body && typeof body.detail === "string") detail = body.detail;
  } catch {
    // non-JSON error body; keep statusText
  }
  throw new ApiError(resp.status, detail);
}

// ── SSE progress stream (reconnecting via EventSource) ──

export interface ProgressEvent {
  node: string;
  status: string;
  percent: number;
  message: string;
}

export function openProgressStream(
  jobId: string,
  onEvent: (ev: ProgressEvent) => void,
  onStatus: (state: "connecting" | "open" | "closed" | "error") => void
): () => void {
  const key = getApiKey();
  const url =
    apiBase() +
    "/jobs/" +
    encodeURIComponent(jobId) +
    "/progress?key=" +
    encodeURIComponent(key);
  const es = new EventSource(url);
  onStatus("connecting");
  es.onopen = () => onStatus("open");
  es.onmessage = (ev: MessageEvent) => {
    try {
      onEvent(JSON.parse(ev.data) as ProgressEvent);
    } catch {
      // ignore malformed frames
    }
  };
  es.onerror = () => onStatus("error");
  return () => {
    es.close();
    onStatus("closed");
  };
}

export async function downloadCapsule(jobId: string, name?: string): Promise<void> {
  let path = "/api/v1/jobs/" + encodeURIComponent(jobId) + "/capsule";
  if (name) path += "?name=" + encodeURIComponent(name);
  const resp = await fetch(apiBase() + path, { headers: headers() });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      // keep statusText
    }
    throw new ApiError(resp.status, detail);
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name || "capsule.zip";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ── Response shapes (mirror api/routes/web.py) ──

export interface Job {
  id: string;
  repo_path?: string;
  base_ref?: string;
  head_ref?: string;
  spec_path?: string;
  status?: string;
  depth?: string;
  retry_count?: number;
  worker_id?: string;
  last_error?: string;
  created_at?: string;
  updated_at?: string;
  summary?: unknown;
}

export interface DashboardData {
  degraded: boolean;
  degraded_reasons: string[];
  generated_at: string;
  jobs: {
    total: number;
    by_status: Record<string, number>;
    failure_rate: number | null;
    blocked_rate: number | null;
  };
  timeline_24h: { hour: string; count: number; failed: number }[];
  timeline_timezone: string;
  cost: { available: boolean; currency: string; total_usd: number | null; reason: string };
  tokens: { available: boolean; total: number | null; reason: string };
  recent_jobs: Job[];
}

export interface Stage {
  node: string;
  status: string;
  percent: number;
  message: string;
  at: string;
  event_id: string;
}

export interface StagesData {
  job_id: string;
  stages: Stage[];
  event_count: number;
  degraded: boolean;
  degraded_reason: string | null;
}

export interface Finding {
  id?: string;
  severity?: string;
  contract_id?: string;
  confidence?: number;
  evidence_type?: string;
  type?: string;
  location?: string;
  description?: string;
  impact_path?: unknown;
  capsule_path?: string;
}

export interface FindingsData {
  job_id: string;
  findings: Finding[];
  count: number;
  degraded: boolean;
  degraded_reason: string | null;
}

export interface CertificateData {
  job_id: string;
  path: string;
  document: Record<string, unknown>;
  signed_statement?: Record<string, unknown>;
  signed_path?: string;
}

export interface MatrixRow {
  contract_id_str: string;
  requirement_text: string;
  checker_type: string;
  expected_behavior: string;
  result: string;
  evidence_ref: string;
}

export interface MatrixData {
  job_id: string;
  rows: MatrixRow[];
  counts: { total: number; passed: number; failed: number; unverified: number };
  degraded: boolean;
  degraded_reason: string | null;
}

export interface ContractRow {
  id: string;
  repo_path: string;
  requirement_ref: string;
  requirement: string;
  checker_type: string;
  expected_behavior: string;
  source: string;
  version: number;
  status: string;
  spec_digest: string;
  created_at?: string;
  updated_at?: string;
}

export interface ContractsData {
  contracts: ContractRow[];
  count: number;
  filter: { status: string; repo_path: string | null };
  degraded: boolean;
}

export interface EvalData {
  source: string;
  modified_at: string;
  report: {
    total_cases?: number;
    should_detect?: number;
    detected?: number;
    false_positives?: number;
    precision?: number;
    recall?: number;
    f1?: number;
    cases?: {
      case?: string;
      verdict?: string;
      should_detect?: boolean;
      expected_severity?: string;
      expected_evidence?: string;
      matched_findings?: number;
      matched_severities?: string;
      contracts_found?: string;
      expected_contract?: string;
    }[];
  };
}

export interface HealthCheck {
  ok: boolean;
  latency_ms: number;
  error: string | null;
}

export interface HealthData {
  status: string;
  degraded: boolean;
  checks: Record<string, HealthCheck>;
}

// ── SpecCraft Agent console (mirror api/routes/agent_console.py) ──

export interface AgentJobSummary {
  id: string;
  task_name: string;
  repo_path: string;
  status: string;
  plan_steps: number;
  events_count: number;
  approvals_count: number;
  created_at: string;
  updated_at: string;
}

export interface AgentProgress {
  percent: number;
  current_step: number;
  message: string;
  updated_at: string;
}

export interface AgentPlanStep {
  index: number;
  title: string;
  summary: string;
  status: string;
  approval?: { decision: string; note: string | null; at: string } | null;
}

export interface AgentPlan {
  version: number;
  steps: AgentPlanStep[];
  created_at?: string;
}

export interface AgentJobResult {
  verdict: string;
  reason: string | null;
}

export interface AgentJob {
  id: string;
  task_name: string;
  repo_path: string;
  spec_text: string;
  status: string;
  plan: AgentPlan | null;
  progress: AgentProgress;
  result: AgentJobResult | null;
  worker_id: string | null;
  created_at: string;
  updated_at: string;
  events_count: number;
  approvals_count: number;
}

export interface AgentApproval {
  id: string;
  job_id: string;
  target: "plan" | "step" | "gate";
  step_index: number | null;
  decision: "approve" | "reject";
  note: string | null;
  actor: string;
  created_at: string;
}

export interface AgentEvent {
  seq: number;
  type: "plan" | "tool_call" | "tool_result" | "edit" | "gate" | "progress";
  at: string;
  data: Record<string, unknown>;
}

export interface AgentDiffLine {
  type: "add" | "del" | "context";
  old_no: number | null;
  new_no: number | null;
  text: string;
}

export interface AgentDiffHunk {
  old_start: number;
  old_count: number;
  new_start: number;
  new_count: number;
  lines: AgentDiffLine[];
}

export interface AgentDiffFile {
  path: string;
  status: string;
  hunks: AgentDiffHunk[];
  insertions: number;
  deletions: number;
}

export interface AgentDiff {
  job_id: string;
  mode: "unified" | "split";
  stats: { files_changed: number; insertions: number; deletions: number };
  files: AgentDiffFile[];
  generated_at: string;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const h = headers();
  h["Content-Type"] = "application/json";
  const resp = await fetch(apiBase() + path, {
    method: "POST",
    headers: h,
    body: JSON.stringify(body),
  });
  return handleResponse<T>(resp);
}

// EventSource cannot set headers; the key rides the query string like the
// job progress stream. The stream closes itself with a "done" event once
// the job is terminal.
export function openAgentEventStream(
  jobId: string,
  onEvent: (ev: AgentEvent) => void,
  onStatus: (state: "connecting" | "open" | "closed" | "error") => void,
  onDone?: () => void
): () => void {
  const key = getApiKey();
  const url =
    apiBase() +
    "/agent/jobs/" +
    encodeURIComponent(jobId) +
    "/events?key=" +
    encodeURIComponent(key);
  const es = new EventSource(url);
  onStatus("connecting");
  es.onopen = () => onStatus("open");
  es.onmessage = (ev: MessageEvent) => {
    try {
      onEvent(JSON.parse(ev.data) as AgentEvent);
    } catch {
      // ignore malformed frames
    }
  };
  es.addEventListener("done", () => {
    onStatus("closed");
    if (onDone) onDone();
    es.close();
  });
  es.onerror = () => onStatus("error");
  return () => {
    es.close();
    onStatus("closed");
  };
}

export function listAgentJobs(
  status?: string
): Promise<{ jobs: AgentJobSummary[]; count: number; filter: { status: string | null } }> {
  const q = status && status !== "ALL" ? "?status=" + encodeURIComponent(status) : "";
  return apiGet<{
    jobs: AgentJobSummary[];
    count: number;
    filter: { status: string | null };
  }>("/agent/jobs" + q);
}

export function getAgentJob(jobId: string): Promise<{ job: AgentJob }> {
  return apiGet<{ job: AgentJob }>("/agent/jobs/" + encodeURIComponent(jobId));
}

export function createAgentJob(
  repoPath: string,
  specText: string,
  taskName: string
): Promise<{ job_id: string; status: string }> {
  return apiPost<{ job_id: string; status: string }>("/agent/jobs", {
    repo_path: repoPath,
    spec_text: specText,
    task_name: taskName || null,
  });
}

export function cancelAgentJob(jobId: string): Promise<{ job_id: string; status: string }> {
  return apiPost<{ job_id: string; status: string }>(
    "/agent/jobs/" + encodeURIComponent(jobId) + "/cancel",
    {}
  );
}

export function approveAgentJob(
  jobId: string,
  decision: "approve" | "reject",
  target: "plan" | "step" | "gate",
  note: string,
  stepIndex: number | null
): Promise<{ approval: AgentApproval; job: { id: string; status: string } }> {
  const body: Record<string, unknown> = {
    decision,
    target,
    note: note || null,
  };
  if (stepIndex !== null) body.step_index = stepIndex;
  return apiPost<{
    approval: AgentApproval;
    job: { id: string; status: string };
  }>("/agent/jobs/" + encodeURIComponent(jobId) + "/approve", body);
}

export function listAgentApprovals(
  jobId: string
): Promise<{ job_id: string; approvals: AgentApproval[]; count: number }> {
  return apiGet<{ job_id: string; approvals: AgentApproval[]; count: number }>(
    "/agent/jobs/" + encodeURIComponent(jobId) + "/approvals"
  );
}

export function getAgentDiff(jobId: string, mode: "unified" | "split"): Promise<AgentDiff> {
  return apiGet<AgentDiff>(
    "/agent/jobs/" + encodeURIComponent(jobId) + "/diff?mode=" + mode
  );
}

