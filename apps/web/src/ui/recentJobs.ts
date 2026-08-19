export interface RecentJob {
  path: string;
  label: string;
  at: number;
}

const STORAGE_KEY = "specproof_recent_jobs";
const MAX_JOBS = 6;

function isRecentJob(value: unknown): value is RecentJob {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.path === "string" && typeof v.label === "string" && typeof v.at === "number";
}

/** Recent jobs for the command palette. Pages record entries when a job is
 *  opened; phase 2 page adoption will call recordRecentJob directly. */
export function listRecentJobs(): RecentJob[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isRecentJob).slice(0, MAX_JOBS) : [];
  } catch {
    return [];
  }
}

export function recordRecentJob(path: string, label: string): void {
  try {
    const rest = listRecentJobs().filter((job) => job.path !== path);
    rest.unshift({ path, label, at: Date.now() });
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(rest.slice(0, MAX_JOBS)));
  } catch {
    // storage unavailable; recent list lives for the session only
  }
}
