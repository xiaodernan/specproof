import { useEffect, useMemo, useState } from "react";
import { apiGet, ContractsData } from "../api";
import { Degraded, Empty, ErrorBox, Panel, Spinner, fmtTime } from "../ui";

export default function Contracts() {
  const [data, setData] = useState<ContractsData | null>(null);
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("all");
  const [repoFilter, setRepoFilter] = useState("");

  useEffect(() => {
    let alive = true;
    apiGet<ContractsData>("/api/v1/contracts?status=" + status + (repoFilter ? "&repo_path=" + encodeURIComponent(repoFilter) : ""))
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e) => {
        if (alive) setError(e as Error);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [status, repoFilter]);

  const statusCounts = useMemo(() => {
    const acc: Record<string, number> = {};
    (data ? data.contracts : []).forEach((c) => {
      acc[c.status] = (acc[c.status] || 0) + 1;
    });
    return acc;
  }, [data]);

  return (
    <div>
      <div className="page-head">
        <h1>契约中心 Contract Registry</h1>
        <div className="page-sub">HUMAN APPROVAL WORKFLOW — PROPOSED / APPROVED / REJECTED / REVOKED</div>
      </div>
      <ErrorBox error={error} />

      <Panel
        title="过滤器"
        right={
          <>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="all">全部 ALL</option>
              <option value="approved">已批准 APPROVED</option>
              <option value="proposed">待审 PROPOSED</option>
              <option value="rejected">已驳回 REJECTED</option>
              <option value="revoked">已撤销 REVOKED</option>
            </select>
            <input type="text" placeholder="repo_path 过滤" value={repoFilter} onChange={(e) => setRepoFilter(e.target.value)} />
          </>
        }
      />

      {loading ? (
        <Spinner />
      ) : data ? (
        <>
          {data.degraded ? <Degraded reasons={["registry degraded"]} /> : null}
          <Panel title={"注册表 (" + data.count + ")"}>
            {data.contracts.length === 0 ? (
              <Empty text="注册表为空 (MySQL contract_registry 无行 — 诚实空态)" />
            ) : (
              <table className="data">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Repo</th>
                    <th>状态</th>
                    <th>Requirement</th>
                    <th>Checker</th>
                    <th>Version</th>
                    <th>创建时间</th>
                  </tr>
                </thead>
                <tbody>
                  {data.contracts.map((c) => (
                    <tr key={c.id}>
                      <td className="mono">{c.id}</td>
                      <td className="mono muted">{c.repo_path}</td>
                      <td>
                        <span className={"pill " + (c.status === "APPROVED" ? "pill-ok" : c.status === "REJECTED" || c.status === "REVOKED" ? "pill-bad" : "pill-run")}>
                          {c.status}
                        </span>
                      </td>
                      <td>
                        <div>{c.requirement}</div>
                        <div className="muted mono" style={{ fontSize: 11 }}>
                          {c.requirement_ref} · {c.expected_behavior}
                        </div>
                      </td>
                      <td className="mono">{c.checker_type}</td>
                      <td className="mono">v{c.version}</td>
                      <td className="muted">{fmtTime(c.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
          <Panel title="状态分布">
            <div className="stat-grid">
              {Object.entries(statusCounts).map(([s, n]) => (
                <div className="stat" key={s}>
                  <div className="stat-value">{n}</div>
                  <div className="stat-label">{s}</div>
                </div>
              ))}
            </div>
          </Panel>
        </>
      ) : null}
    </div>
  );
}
