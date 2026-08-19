import { useMemo, useState, type ReactNode } from "react";
import { EmptyState } from "./EmptyState";

export interface Column<T> {
  key: string;
  header: ReactNode;
  width?: string | number;
  align?: "left" | "right" | "center";
  sortable?: boolean;
  sortValue?: (row: T) => string | number;
  render?: (row: T, index: number) => ReactNode;
}

export interface SortState {
  key: string | null;
  dir: "asc" | "desc";
}

export interface TableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string;
  dense?: boolean;
  stickyHeader?: boolean;
  sort?: SortState;
  onSortChange?: (key: string, dir: "asc" | "desc") => void;
  emptyTitle?: string;
  emptyDescription?: string;
  className?: string;
}

export function Table<T>(props: TableProps<T>): JSX.Element {
  const {
    columns,
    rows,
    rowKey,
    dense = false,
    stickyHeader = true,
    sort,
    onSortChange,
    emptyTitle = "暂无数据",
    emptyDescription,
    className,
  } = props;

  const [internalSort, setInternalSort] = useState<SortState>({ key: null, dir: "asc" });
  const controlled = sort !== undefined;
  const sortState = controlled ? sort : internalSort;

  const handleSort = (key: string): void => {
    const next: SortState =
      sortState.key === key
        ? { key, dir: sortState.dir === "asc" ? "desc" : "asc" }
        : { key, dir: "asc" };
    if (!controlled) setInternalSort(next);
    if (onSortChange) onSortChange(key, next.dir);
  };

  const sorted = useMemo(() => {
    if (!sortState.key) return rows;
    const col = columns.find((c) => c.key === sortState.key);
    if (!col || !col.sortable) return rows;
    const get =
      col.sortValue ??
      ((row: T): string | number => {
        const raw = (row as Record<string, unknown>)[col.key];
        return typeof raw === "string" || typeof raw === "number" ? raw : "";
      });
    return [...rows].sort((a, b) => {
      const va = get(a);
      const vb = get(b);
      if (va < vb) return sortState.dir === "asc" ? -1 : 1;
      if (va > vb) return sortState.dir === "asc" ? 1 : -1;
      return 0;
    });
  }, [rows, columns, sortState]);

  const alignClass = (align?: "left" | "right" | "center"): string =>
    align === "right" ? " ui-table-r" : align === "center" ? " ui-table-c" : "";

  const wrapCls =
    "ui-table-wrap" + (className ? " " + className : "");
  const tableCls =
    "ui-table" +
    (dense ? " ui-table-dense" : "") +
    (stickyHeader ? "" : " ui-table-nosticky");

  return (
    <div className={wrapCls}>
      <table className={tableCls}>
        <thead>
          <tr>
            {columns.map((col) => {
              const active = sortState.key === col.key;
              return (
                <th
                  key={col.key}
                  scope="col"
                  style={{ width: col.width }}
                  className={alignClass(col.align)}
                  aria-sort={
                    active && col.sortable
                      ? sortState.dir === "asc"
                        ? "ascending"
                        : "descending"
                      : undefined
                  }
                >
                  {col.sortable ? (
                    <button
                      type="button"
                      className="ui-table-sort"
                      onClick={() => handleSort(col.key)}
                    >
                      {col.header}
                      <span
                        className={"ui-table-caret" + (active ? " ui-table-caret-active" : "")}
                        aria-hidden="true"
                      >
                        {active ? (sortState.dir === "asc" ? "▲" : "▼") : "↕"}
                      </span>
                    </button>
                  ) : (
                    col.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 ? (
            <tr>
              <td className="ui-table-empty" colSpan={columns.length}>
                <EmptyState title={emptyTitle} description={emptyDescription} />
              </td>
            </tr>
          ) : (
            sorted.map((row, i) => (
              <tr key={rowKey(row, i)}>
                {columns.map((col) => {
                  const raw = (row as Record<string, unknown>)[col.key];
                  const cell = col.render
                    ? col.render(row, i)
                    : typeof raw === "string" || typeof raw === "number"
                    ? raw
                    : "";
                  return (
                    <td key={col.key} className={alignClass(col.align)}>
                      {cell}
                    </td>
                  );
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
