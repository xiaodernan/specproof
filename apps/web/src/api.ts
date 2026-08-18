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
