import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { Table, type Column } from "../Table";

interface Row {
  name: string;
  qty: number;
}

const COLUMNS: Column<Row>[] = [
  { key: "name", header: "名称" },
  { key: "qty", header: "库存", align: "right", sortable: true },
  { key: "price", header: "单价", align: "right", sortable: true, sortValue: (r) => (r as unknown as { price: number }).price },
];

const ROWS: Row[] = [
  { name: "荔枝", qty: 128 },
  { name: "山竹", qty: 64 },
  { name: "杨梅", qty: 210 },
];

function bodyTexts(container: HTMLElement): string[] {
  return within(container)
    .getAllByRole("row")
    .slice(1)
    .map((tr) => tr.textContent ?? "");
}

describe("Table", () => {
  it("renders headers and rows", () => {
    render(<Table columns={COLUMNS} rows={ROWS} rowKey={(r) => r.name} />);
    expect(screen.getByRole("columnheader", { name: /名称/ })).toBeTruthy();
    expect(screen.getByText("荔枝")).toBeTruthy();
    expect(screen.getByText("128")).toBeTruthy();
  });

  it("sorts ascending then descending on repeated header clicks", () => {
    const { container } = render(
      <Table columns={COLUMNS} rows={ROWS} rowKey={(r) => r.name} />
    );
    const header = screen.getByRole("button", { name: /库存/ });
    fireEvent.click(header);
    expect(bodyTexts(container)[0]).toContain("山竹"); // 64 first
    expect(container.querySelector('th[aria-sort="ascending"]')).toBeTruthy();
    fireEvent.click(header);
    expect(bodyTexts(container)[0]).toContain("杨梅"); // 210 first
    expect(container.querySelector('th[aria-sort="descending"]')).toBeTruthy();
  });

  it("uses the custom sortValue when provided", () => {
    const rows: Array<Row & { price: number }> = [
      { name: "A", qty: 1, price: 30 },
      { name: "B", qty: 2, price: 10 },
      { name: "C", qty: 3, price: 20 },
    ];
    const { container } = render(
      <Table columns={COLUMNS} rows={rows} rowKey={(r) => r.name} />
    );
    fireEvent.click(screen.getByRole("button", { name: /单价/ }));
    expect(bodyTexts(container)[0]).toContain("B");
  });

  it("renders the empty state when there are no rows", () => {
    render(
      <Table
        columns={COLUMNS}
        rows={[]}
        rowKey={(r) => r.name}
        emptyTitle="没有契约"
        emptyDescription="先创建一个契约"
      />
    );
    expect(screen.getByText("没有契约")).toBeTruthy();
    expect(screen.getByText("先创建一个契约")).toBeTruthy();
  });
});
