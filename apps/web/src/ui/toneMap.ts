// Pure tone mapping for severity and result/evidence status pills.
//
// Two independent maps, on purpose: severity (BLOCKER/MAJOR/MINOR/INFO) and
// result/evidence status (PASS/FAIL/UNVERIFIED/DEGRADED) must never share a
// tone scale — conflating them once rendered UNVERIFIED with a green PASS
// tone. Every unknown/missing value renders 未知 UNKNOWN in the neutral
// tone; no branch of either map ever returns a green class for anything
// other than a verified pass.

export interface PillSpec {
  /** Suffix for the base .pill class, e.g. "pill-ok". */
  cls: string;
  /** Exact text rendered inside the pill. */
  label: string;
}

const UNKNOWN: PillSpec = { cls: "pill-mute", label: "未知 UNKNOWN" };

/**
 * Severity tone map: BLOCKER red, MAJOR orange, MINOR yellow, INFO neutral.
 * Anything else (absent, empty, unrecognized) is 未知 in the neutral tone.
 */
export function severityPill(severity?: string | null): PillSpec {
  switch ((severity || "").toUpperCase()) {
    case "BLOCKER":
      return { cls: "pill-bad", label: "BLOCKER" };
    case "MAJOR":
      return { cls: "pill-major", label: "MAJOR" };
    case "MINOR":
      return { cls: "pill-minor", label: "MINOR" };
    case "INFO":
      return { cls: "pill-mute", label: "INFO" };
    default:
      return { ...UNKNOWN };
  }
}

/**
 * Result / evidence status map: PASS green, FAIL red, UNVERIFIED amber,
 * DEGRADED neutral. Anything else renders 未知 in the neutral tone —
 * never green.
 */
export function resultPill(result?: string | null): PillSpec {
  switch ((result || "").toUpperCase()) {
    case "PASS":
      return { cls: "pill-ok", label: "PASS" };
    case "FAIL":
      return { cls: "pill-bad", label: "FAIL" };
    case "UNVERIFIED":
      return { cls: "pill-unverified", label: "UNVERIFIED" };
    case "DEGRADED":
      return { cls: "pill-mute", label: "DEGRADED" };
    default:
      return { ...UNKNOWN };
  }
}
