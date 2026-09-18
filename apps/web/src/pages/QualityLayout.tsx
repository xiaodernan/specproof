import type { ReactNode } from "react";
import { Button } from "../ui";
import { ProductIcon, type ProductIconName } from "../ui/ProductIcon";
import "../styles/quality.css";

export function QualityHeader({ eyebrow, title, description, icon, action }: {
  eyebrow: string; title: string; description: string; icon: ProductIconName; action?: ReactNode;
}) {
  return <header className="quality-heading"><div className="quality-heading-copy"><span className="quality-eyebrow"><ProductIcon name={icon} size={15} />{eyebrow}</span><h1>{title}</h1><p>{description}</p></div>{action && <div className="quality-heading-action">{action}</div>}</header>;
}

export function QualityEmpty({ icon, title, description, action }: { icon: ProductIconName; title: string; description: string; action?: ReactNode }) {
  return <div className="quality-empty"><span className="quality-empty-icon"><ProductIcon name={icon} size={26} /></span><h3>{title}</h3><p>{description}</p>{action}</div>;
}

export function QualityPagination({ page, pageSize, total, onChange }: { page: number; pageSize: number; total: number; onChange: (page: number) => void }) {
  if (total <= pageSize) return null;
  const pages = Math.ceil(total / pageSize);
  return <nav className="quality-pagination" aria-label="表格分页"><span>第 {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} 条，共 {total} 条</span><div><Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>上一页</Button><span>{page} / {pages}</span><Button variant="ghost" size="sm" disabled={page >= pages} onClick={() => onChange(page + 1)}>下一页</Button></div></nav>;
}
