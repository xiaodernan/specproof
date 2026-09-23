import { useMemo, useState } from "react";
import type { ContractsData } from "../api";
import { useDebouncedValue, useRemoteData } from "../hooks/useRemoteData";
import { Button, Degraded, ErrorBox, Input, Panel, Select, Spinner, StatCard, Table, Term, checkerLabel, contractStatusLabel, CONTRACT_STATUS_CN, fmtTime } from "../ui";
import { ProductIcon } from "../ui/ProductIcon";
import { QualityEmpty, QualityHeader, QualityPagination } from "./QualityLayout";

const PAGE_SIZE = 25;

type ContractRule = ContractsData["contracts"][number];

export default function Contracts() {
  const [status, setStatus] = useState("all");
  const [repoFilter, setRepoFilter] = useState("");
  const [page, setPage] = useState(1);
  const repo = useDebouncedValue(repoFilter);
  const { data, error, loading, refreshing, refresh } = useRemoteData<ContractsData>(
    "/api/v1/contracts?status=" + status + (repo ? "&repo_path=" + encodeURIComponent(repo) : ""),
  );
  const counts = useMemo(() => {
    const result: Record<string, number> = {};
    data?.contracts.forEach(rule => { const key = rule.status.toUpperCase(); result[key] = (result[key] || 0) + 1; });
    return result;
  }, [data]);
  const contracts = data?.contracts ?? [];
  const currentPage = Math.min(page, Math.max(1, Math.ceil(contracts.length / PAGE_SIZE)));
  const filtered = status !== "all" || !!repo;
  const clear = () => { setStatus("all"); setRepoFilter(""); setPage(1); };

  return <div className="quality-page">
    <QualityHeader icon="contracts" eyebrow="ACCEPTANCE RULES" title="把需求，变成可检查的规则。" description="规则说明代码必须满足什么行为。查看预期结果、检查方式和审核状态，让团队对“完成”的定义保持一致。" action={<Button variant="ghost" loading={refreshing} onClick={refresh}>刷新规则</Button>} />
    <div className="quality-brief"><ProductIcon name="guide" /><p><strong>规则如何产生？</strong> 从一次变更验收开始，系统根据需求文件提取<Term id="contract">契约</Term>。这里汇总已登记的规则；待审核、已驳回和已撤销的规则，都不能当作已批准的验收依据。<a href="#/guide">了解完整流程 ↗</a></p></div>
    <div className="quality-filters">
      <Select label="审核状态" value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option value="all">全部状态</option>{Object.entries(CONTRACT_STATUS_CN).map(([value, label]) => <option key={value} value={value.toLowerCase()}>{label}</option>)}</Select>
      <Input className="quality-filter-wide" label="项目路径" type="search" value={repoFilter} placeholder="输入完整仓库路径，精确匹配" maxLength={512} onChange={event => { setRepoFilter(event.target.value); setPage(1); }} />
      {(filtered || !!repoFilter) && <Button variant="ghost" onClick={clear}>清除筛选</Button>}
    </div>
    <ErrorBox error={error} />
    {loading ? <Spinner /> : error ? <QualityEmpty icon="contracts" title="暂时无法读取规则" description="请确认服务连接，然后重试。读取失败不会被当作规则为空。" action={<Button onClick={refresh}>重新加载</Button>} /> : data && <>
      {data.degraded && <Degraded reasons={["规则数据暂不完整，恢复服务后请重新加载。"]} />}
      <div className="quality-metrics" aria-label="当前筛选规则概况"><StatCard label="符合筛选的规则" value={data.count} tone="info" /><StatCard label="已批准" value={counts.APPROVED ?? 0} tone="ok" /><StatCard label="待审核" value={counts.PROPOSED ?? 0} tone="warn" /><StatCard label="已驳回 / 撤销" value={(counts.REJECTED ?? 0) + (counts.REVOKED ?? 0)} tone="mute" /></div>
      <Panel title="规则清单" right={<span className="muted">按创建时间排序</span>}>
        {!contracts.length ? <QualityEmpty icon="contracts" title={filtered ? "没有找到符合条件的规则" : "让第一次验收沉淀为规则"} description={filtered ? "尝试其他状态，或清除项目路径筛选。项目路径需要与登记路径完全一致。" : "准备明确的需求文件，创建一次变更验收。系统会提取可验证的行为，规则登记后可在这里查看。"} action={filtered ? <Button onClick={clear}>清除筛选</Button> : <a className="btn btn-primary" href="#/jobs/new">创建变更验收 →</a>} /> : <>
          <Table<ContractRule>
            className="quality-table"
            rows={contracts.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)}
            rowKey={(rule) => rule.id}
            columns={[
              {
                key: "requirement",
                header: "需求与规则",
                render: (rule) => (
                  <>
                    <strong>{rule.requirement || "未提供需求描述"}</strong>
                    <span className="quality-cell-secondary mono">{rule.id} · v{rule.version}</span>
                    {rule.requirement_ref && <span className="quality-cell-secondary">需求来源：{rule.requirement_ref}</span>}
                  </>
                ),
              },
              {
                key: "expected",
                header: "预期行为",
                render: (rule) => <span className="quality-cell-copy">{rule.expected_behavior || "尚未提供"}</span>,
              },
              {
                key: "status",
                header: "审核状态",
                render: (rule) => {
                  const code = rule.status.toUpperCase();
                  const cls = code === "APPROVED" ? "pill-ok" : code === "PROPOSED" ? "pill-run" : "pill-mute";
                  return <span className={"pill " + cls} title={rule.status}>{contractStatusLabel(rule.status)}</span>;
                },
              },
              {
                key: "checker",
                header: "检查方式",
                render: (rule) => <span className="mono" title={rule.checker_type || undefined}>{checkerLabel(rule.checker_type)}</span>,
              },
              {
                key: "repo",
                header: "项目 / 创建时间",
                render: (rule) => (
                  <>
                    <span className="quality-cell-copy mono">{rule.repo_path}</span>
                    <span className="quality-cell-secondary">{fmtTime(rule.created_at)}</span>
                  </>
                ),
              },
            ]}
          /><QualityPagination page={currentPage} pageSize={PAGE_SIZE} total={contracts.length} onChange={setPage} />
        </>}
      </Panel>
    </>}
  </div>;
}
