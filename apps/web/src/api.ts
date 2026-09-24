// Unified API client: fetch + SSE, explicit errors and degradation states.
// Credentials live in sessionStorage and travel in request headers,
// including authenticated fetch-based SSE streams.
//
// Multi-tenant mode (industrialization phase 1): a Bearer token (local
// sp_* or an OIDC id_token) may be stored instead; when present it is sent
// as Authorization and takes precedence over the legacy X-API-Key.

export class ApiError extends Error {
  status: number;
  detail: string;
  code?: string;
  requestId?: string;
  constructor(status: number, detail: string, code?: string, requestId?: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.code = code;
    this.requestId = requestId;
  }
}

const KEY_STORAGE = "specproof_api_key";
const BASE_STORAGE = "specproof_api_base";
const BEARER_STORAGE = "specproof_bearer_token";
const SAVED_TOKENS_STORAGE = "specproof_saved_tokens";

export function getBearerToken(): string {
  try {
    return window.sessionStorage.getItem(BEARER_STORAGE) || "";
  } catch {
    return "";
  }
}

export function setBearerToken(token: string): void {
  try {
    window.sessionStorage.setItem(BEARER_STORAGE, token);
  } catch {
    // storage unavailable; token lives only in memory
  }
}

export function clearBearerToken(): void {
  try {
    window.sessionStorage.removeItem(BEARER_STORAGE);
  } catch {
    // ignore
  }
}

export interface SavedToken {
  name: string;
  token: string;
}

// Saved tokens let one browser hold credentials for several tenants; the
// tenant switcher activates one of them. Cleartext lives in localStorage
// (same trust model as the sessionStorage API key).
export function listSavedTokens(): SavedToken[] {
  try {
    const raw = window.localStorage.getItem(SAVED_TOKENS_STORAGE);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as SavedToken[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveToken(name: string, token: string): void {
  try {
    const rest = listSavedTokens().filter((t) => t.token !== token);
    rest.unshift({ name: name || "token-" + (rest.length + 1), token });
    window.localStorage.setItem(SAVED_TOKENS_STORAGE, JSON.stringify(rest));
  } catch {
    // ignore
  }
}

export function removeSavedToken(token: string): void {
  try {
    const rest = listSavedTokens().filter((t) => t.token !== token);
    window.localStorage.setItem(SAVED_TOKENS_STORAGE, JSON.stringify(rest));
  } catch {
    // ignore
  }
}

export function consumeOidcCallback(): boolean {
  // The OIDC callback lands on /#oidc_token=...; stash the id_token and
  // drop the fragment so it never leaks into history or logs.
  try {
    const hash = window.location.hash || "";
    const match = hash.match(/oidc_token=([^&]+)/);
    if (!match) return false;
    setBearerToken(decodeURIComponent(match[1]));
    window.location.hash = "#/dashboard";
    return true;
  } catch {
    return false;
  }
}

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
  const bearer = getBearerToken();
  if (bearer) {
    h["Authorization"] = "Bearer " + bearer;
  } else {
    const key = getApiKey();
    if (key) h["X-API-Key"] = key;
  }
  return h;
}

// A rejected fetch means the request never reached the API: backend down,
// wrong base URL, offline, or blocked by CORS. The browser's raw "Failed to
// fetch" must not leak to a Chinese UI, so translate it into an actionable
// message. AbortError is rethrown untouched so caller-driven cancellations
// (AbortSignal) are never mistaken for a connectivity failure.
export const NETWORK_UNREACHABLE =
  "无法连接到服务，请确认后端已启动、API 地址填写正确（见「模型连接 / 设置」），并在网络可用后重试。";

async function doFetch(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, NETWORK_UNREACHABLE);
  }
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const resp = await doFetch(apiBase() + path, { headers: headers(), signal });
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
  let detail = resp.statusText || "请求失败，请稍后重试";
  let code: string | undefined;
  let requestId = resp.headers.get("X-Request-ID") || undefined;
  try {
    const body = await resp.json();
    if (body && typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body?.detail)) {
      detail = body.detail.map((item: { loc?: string[]; msg?: string }) =>
        [item.loc?.filter((part) => part !== "body").join("."), item.msg].filter(Boolean).join(": ")
      ).join("；");
    } else if (typeof body?.error?.message === "string") detail = body.error.message;
    if (typeof body?.code === "string") code = body.code;
    else if (typeof body?.error?.code === "string") code = body.error.code;
    if (typeof body?.request_id === "string") requestId = body.request_id;
    else if (typeof body?.error?.request_id === "string") requestId = body.error.request_id;
  } catch {
    // non-JSON error body; keep statusText
  }
  throw new ApiError(resp.status, detail, code, requestId);
}

// ── SSE progress stream with authenticated reconnects ──
// §14.3 payload per api/routes/jobs.py _progress_payload:
// { seq, job, type, stage, status, percentage, summary, ts }.
// The legacy worker fields (node/percent/message) stay accepted as
// fallback when the new payload is absent (older backends).
export interface ProgressEvent {
  seq?: number;
  sequence?: number;
  job?: string;
  type?: string;
  stage?: string;
  status?: string;
  percentage?: number;
  summary?: string;
  ts?: string;
  // legacy fallback fields
  node?: string;
  percent?: number;
  message?: string;
}

export function openProgressStream(
  jobId: string,
  onEvent: (ev: ProgressEvent) => void,
  onStatus: (state: "connecting" | "open" | "closed" | "error") => void
): () => void {
  return openEventStream("/jobs/" + encodeURIComponent(jobId) + "/progress", (type, data) => {
    if (type === "message" || type === "progress") onEvent(data as ProgressEvent);
  }, onStatus);
}

type StreamState = "connecting" | "open" | "closed" | "error";

// Fetch streams carry the same Authorization headers as every other API
// request. They also handle named SSE events, which EventSource.onmessage
// silently misses. Keep the last event id across reconnects for safe replay.
function openEventStream(
  path: string,
  onEvent: (type: string, data: unknown) => void,
  onStatus: (state: StreamState) => void,
  onDone?: () => void,
): () => void {
  let stopped = false;
  let lastId = "";
  let retry = 1000;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let controller: AbortController;

  const connect = async () => {
    if (stopped) return;
    controller = new AbortController();
    onStatus("connecting");
    try {
      const requestHeaders = { ...headers(), Accept: "text/event-stream" };
      if (lastId) Object.assign(requestHeaders, { "Last-Event-ID": lastId });
      const response = await fetch(apiBase() + path, { headers: requestHeaders, signal: controller.signal });
      if (stopped) { await response.body?.cancel(); return; }
      if (!response.ok) await handleResponse(response);
      if (!response.body) throw new Error("实时进度连接不可用");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let eventType = "message";
      let frameId: string | undefined;
      let dataLines: string[] = [];
      onStatus("open");
      const consumeLine = (line: string) => {
        if (!line) {
          if (frameId !== undefined) lastId = frameId;
          frameId = undefined;
          if (eventType === "done") {
            stopped = true;
            controller.abort();
            onStatus("closed");
            onDone?.();
          } else if (dataLines.length) {
            let data: unknown;
            try { data = JSON.parse(dataLines.join("\n")); } catch { dataLines = []; eventType = "message"; return; }
            retry = 1000;
            onEvent(eventType, data);
          }
          dataLines = [];
          eventType = "message";
          return;
        }
        const colon = line.indexOf(":");
        const field = colon === -1 ? line : line.slice(0, colon);
        const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
        if (field === "data") dataLines.push(value);
        if (field === "event") eventType = value;
        if (field === "id" && !value.includes("\0")) frameId = value;
      };
      try {
        while (!stopped) {
          const part = await reader.read();
          if (part.done) break;
          buffer += decoder.decode(part.value, { stream: true });
          let end: number;
          while ((end = buffer.indexOf("\n")) >= 0 && !stopped) {
            consumeLine(buffer.slice(0, end).replace(/\r$/, ""));
            buffer = buffer.slice(end + 1);
          }
        }
      } finally {
        reader.releaseLock();
      }
      if (!stopped) throw new Error("实时连接已断开");
    } catch (error) {
      if (stopped) return;
      onStatus("error");
      // A permission failure needs a new login, not an endless retry loop.
      if (error instanceof ApiError && (error.status === 401 || error.status === 403 || error.status === 404)) return;
      timer = setTimeout(connect, retry);
      retry = Math.min(retry * 2, 15000);
    }
  };
  void connect();
  return () => {
    stopped = true;
    clearTimeout(timer);
    controller?.abort();
    onStatus("closed");
  };
}

export async function downloadCapsule(jobId: string, name?: string): Promise<void> {
  let path = "/api/v1/jobs/" + encodeURIComponent(jobId) + "/capsule";
  if (name) path += "?name=" + encodeURIComponent(name);
  const resp = await doFetch(apiBase() + path, { headers: headers() });
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
  is_demo?: boolean | number;
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

export interface VerificationRequest {
  repo_path: string;
  spec_path: string;
  base_ref: string;
  head_ref: string;
  depth: "FAST";
}

export function createVerification(payload: VerificationRequest): Promise<{ job_id: string; status: string }> {
  return apiPost("/jobs", payload);
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
  /**
   * Differential attribution — only present for rows the pipeline produced
   * (the persisted summary), absent for declaration-only table rows. A
   * missing value means "no differential experiment ran for this rule", and
   * must never be rendered as a pass.
   */
  attribution?: string;
  base_result?: string;
  head_result?: string;
  experiment?: string;
  unverified_reason?: string;
  next_action?: string;
  severity?: string;
  evidence_type?: string;
  location?: string;
  finding_id?: string;
  /**
   * WHERE the differential experiment actually executed:
   * `docker_sandbox` | `local_host_no_sandbox` | `unconfirmed`. Absent for
   * rules with no differential run. This is a safety disclosure — a host run
   * executed the untrusted change's own tests on the operator's machine — so
   * an unknown value must be shown verbatim, never rounded to "sandboxed".
   */
  execution_surface?: string;
}

export interface MatrixData {
  job_id: string;
  rows: MatrixRow[];
  counts: { total: number; passed: number; failed: number; unverified: number };
  /** Which numbers the counts came from: the returned rows, or the pipeline's
   *  own totals when the row list was deliberately truncated for size. */
  counts_source?: string;
  rows_total?: number;
  rows_truncated?: boolean;
  sources?: {
    mysql_summary_matrix_rows?: boolean;
    mysql_contracts_table?: boolean;
  };
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
    negative_cases?: number;
    // Undefined when the sample denominator is 0: an empty positive set has no
    // recall to report, so the API emits null rather than a vacuous 100%.
    precision?: number | null;
    recall?: number | null;
    f1?: number | null;
    acceptance?: { status?: string; passed?: boolean };
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

// Health payload fields are optional by contract: the API answers with
// what it measured and the UI must render missing fields as 未知 instead of
// inventing a status (§14.4 honest five-category health).
export interface HealthCheck {
  ok?: boolean;
  latency_ms?: number;
  error?: string | null;
}

export interface HealthData {
  status?: string;
  degraded?: boolean;
  degraded_reasons?: string[];
  capabilities?: unknown[] | Record<string, unknown>;
  checks?: Record<string, HealthCheck>;
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
  current_step: number | string;
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
  diff_stat?: { files_changed: number; files?: string[] };
  gates?: { overall: string; overall_note?: string; gates?: { gate: string; status: string; note?: string }[] };
  llm_usage?: { calls?: number; total_tokens?: number; prompt_tokens?: number; completion_tokens?: number; calls_detail?: { model?: string }[] };
  cost_unavailable_reason?: string;
}

export interface AgentJob {
  id: string;
  task_name: string;
  repo_path: string;
  spec_text: string;
  execution_mode?: "llm" | "deterministic" | null;
  status: string;
  plan: AgentPlan | null;
  progress: AgentProgress;
  result: AgentJobResult | null;
  /**
   * The independent accept projection (W35.1) — the only record that says
   * whether this change was ACCEPTED, as opposed to merely developed.
   * `null` means no projection is attached (the page must pair it with job
   * status: a running job has none YET, a finished job has none);
   * `{ malformed: true }` means one exists but cannot be read, which is a
   * different fact and must never render as "没有验收记录".
   */
  accept?: AgentAccept | null;
  worker_id: string | null;
  created_at: string;
  updated_at: string;
  events_count: number;
  approvals_count: number;
}

export interface AgentAcceptGateEntry {
  gate: string;
  status: string;
  note: string;
  duration_ms?: number | null;
  findings_total: number;
}

export interface AgentAcceptGates {
  overall: string;
  overall_note: string;
  summary: string;
  duration_ms?: number | null;
  entries: AgentAcceptGateEntry[];
  total: number;
  truncated: boolean;
}

export interface AgentAccept {
  attached: boolean;
  malformed: boolean;
  verdict?: string;
  note?: string;
  rolled_back?: boolean;
  idempotent?: boolean;
  certificate_path?: string;
  rejection_notice_path?: string;
  gates?: AgentAcceptGates;
  findings?: Record<string, unknown>[];
  findings_total?: number;
  findings_truncated?: boolean;
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
  type: "plan" | "tool_call" | "tool_result" | "edit" | "gate" | "progress" | "model_output";
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

export async function apiDelete<T>(path: string): Promise<T> {
  const resp = await doFetch(apiBase() + path, { method: "DELETE", headers: headers() });
  return handleResponse<T>(resp);
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const h = headers();
  h["Content-Type"] = "application/json";
  const resp = await doFetch(apiBase() + path, {
    method: "POST",
    headers: h,
    body: JSON.stringify(body),
  });
  return handleResponse<T>(resp);
}

// The stream closes itself with a "done" event once the job is terminal.
export function openAgentEventStream(
  jobId: string,
  onEvent: (ev: AgentEvent) => void,
  onStatus: (state: "connecting" | "open" | "closed" | "error") => void,
  onDone?: () => void
): () => void {
  return openEventStream("/agent/jobs/" + encodeURIComponent(jobId) + "/events", (_type, data) => {
    onEvent(data as AgentEvent);
  }, onStatus, onDone);
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
  taskName: string,
  executionMode: "llm" | "deterministic" = "llm"
): Promise<{ job_id: string; status: string }> {
  return apiPost<{ job_id: string; status: string }>("/agent/jobs", {
    repo_path: repoPath,
    spec_text: specText,
    task_name: taskName || null,
    execution_mode: executionMode,
    plan_first: true,
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

// ── Multi-tenant identity (mirror api/routes/admin.py) ──

export interface AuthConfig {
  auth_mode: string;
  oidc: { enabled: boolean; issuer: string; client_id: string };
}

export interface PrincipalInfo {
  user_id: string;
  tenant_id: string;
  roles: string[];
  scopes: string[];
  email?: string;
}

export interface TenantRow {
  id: string;
  name: string;
  plan_id: string;
  status: string;
  created_at: number;
}

export interface UserRow {
  id: string;
  tenant_id: string;
  email: string;
  role: string;
  status: string;
  created_at: number;
}

export interface TokenRow {
  id: string;
  user_id: string;
  user_email: string;
  name: string;
  scopes: string;
  expires_at: number | null;
  last_used_at: number | null;
  created_at: number;
}

export function getAuthConfig(): Promise<AuthConfig> {
  return apiGet<AuthConfig>("/auth/config");
}

export function getAuthMe(): Promise<{ principal: PrincipalInfo }> {
  return apiGet<{ principal: PrincipalInfo }>("/auth/me");
}

export function listTenants(): Promise<{ tenants: TenantRow[]; count: number }> {
  return apiGet<{ tenants: TenantRow[]; count: number }>("/api/v1/admin/tenants");
}

export function createTenant(
  name: string,
  planId: string
): Promise<{ tenant: TenantRow }> {
  return apiPost<{ tenant: TenantRow }>("/api/v1/admin/tenants", {
    name,
    plan_id: planId || "free",
  });
}

export function listUsers(tenantId?: string): Promise<{ users: UserRow[]; count: number }> {
  const q = tenantId ? "?tenant_id=" + encodeURIComponent(tenantId) : "";
  return apiGet<{ users: UserRow[]; count: number }>("/api/v1/admin/users" + q);
}

export function createUser(email: string, role: string): Promise<{ user: UserRow }> {
  return apiPost<{ user: UserRow }>("/api/v1/admin/users", { email, role });
}

export function setUserRole(userId: string, role: string): Promise<{ user: UserRow }> {
  return apiPost<{ user: UserRow }>(
    "/api/v1/admin/users/" + encodeURIComponent(userId) + "/role",
    { role }
  );
}

export function setUserStatus(userId: string, status: string): Promise<{ user: UserRow }> {
  return apiPost<{ user: UserRow }>(
    "/api/v1/admin/users/" + encodeURIComponent(userId) + "/status",
    { status }
  );
}

export function listTokens(): Promise<{ tokens: TokenRow[]; count: number }> {
  return apiGet<{ tokens: TokenRow[]; count: number }>("/api/v1/admin/tokens");
}

export function createToken(
  name: string,
  scopes: string,
  userId?: string
): Promise<{ token: TokenRow; cleartext: string }> {
  const body: Record<string, unknown> = { name, scopes };
  if (userId) body.user_id = userId;
  return apiPost<{ token: TokenRow; cleartext: string }>("/api/v1/admin/tokens", body);
}

export function revokeToken(tokenId: string): Promise<{ revoked: boolean; token_id: string }> {
  return apiDelete<{ revoked: boolean; token_id: string }>(
    "/api/v1/admin/tokens/" + encodeURIComponent(tokenId)
  );
}

