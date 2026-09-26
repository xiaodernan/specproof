// #96: the audit trail's four job dispositions, glossed once.
//
// The backend owns this vocabulary (`storage/mysql.py::AUDIT_JOB_*`) and
// `list_audit_logs` stamps every row with `job_disposition`. This file is the
// only place in apps/web allowed to enumerate it;
// tests/unit/test_audit_disposition_labels.py reconciles the two sets in both
// directions, so a fifth state added server-side cannot render as 未登记 here,
// and a gloss invented here cannot exist that nothing produces (#81's lesson).

export interface AuditDispositionSpec {
  label: string;
  hint: string;
  cls: string;
}

export const AUDIT_DISPOSITIONS: Record<string, AuditDispositionSpec> = {
  present: {
    label: "作业在册",
    hint: "这条审计指向的作业仍然在系统里，可以打开作业看完整证据。",
    cls: "pill-ok",
  },
  purged_by_lifecycle: {
    label: "作业已按数据生命周期删除",
    hint: "作业行被显式删除，并在同一事务里留下了删除说明；审计日志按 DATA_LIFECYCLE §3.1 有意保留，所以这条记录仍然有效、可查。",
    cls: "pill-mute",
  },
  system_level: {
    label: "系统级记录",
    hint: "这条审计本来就不针对某个作业（没有作业号），例如跨租户访问被拒。",
    cls: "pill-mute",
  },
  unexplained: {
    label: "引用无法解释",
    hint: "作业既不在册，也没有删除说明——不能判定它是否存在过，需要人工排查（多为历史测试残留）。",
    cls: "pill-bad",
  },
};

// An unregistered value is reported as such. Guessing "probably fine" here is
// how a schema change silently becomes a wrong audit statement.
const UNREGISTERED: AuditDispositionSpec = {
  label: "未登记状态",
  hint: "后端返回了一个词表之外的作业去向，无法给出解释，请核对版本是否一致。",
  cls: "pill-unverified",
};

export function auditDisposition(raw?: string | null): AuditDispositionSpec {
  if (!raw) return UNREGISTERED;
  return AUDIT_DISPOSITIONS[raw] || { ...UNREGISTERED, label: "未登记状态 · " + raw };
}

export function auditDispositionKeys(): string[] {
  return Object.keys(AUDIT_DISPOSITIONS);
}

// RBAC per api/routes/admin.py list_audit: admin OR auditor only — operator is
// deliberately not included, unlike the billing console. The Python parity
// gate reads the handler's own frozenset and fails if these two drift.
export const AUDIT_ROLES: string[] = ["admin", "auditor"];
