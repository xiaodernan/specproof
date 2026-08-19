/**
 * Tree view provider for the Plan sidebar: the plan document rendered as a
 * JSON tree (generic object/array walk with dedicated step nodes).
 */

import * as vscode from "vscode";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stepStatusIcon(status: string): string {
  if (status === "approved") return "check";
  if (status === "rejected") return "error";
  if (status === "running") return "sync~spin";
  return "circle-outline";
}

export class PlanTreeItem extends vscode.TreeItem {
  constructor(
    label: string,
    public readonly children?: PlanTreeItem[],
    options: {
      description?: string;
      tooltip?: string;
      contextValue?: string;
      icon?: vscode.ThemeIcon;
    } = {},
  ) {
    super(
      label,
      children && children.length > 0
        ? vscode.TreeItemCollapsibleState.Expanded
        : vscode.TreeItemCollapsibleState.None,
    );
    this.description = options.description;
    this.tooltip = options.tooltip;
    this.contextValue = options.contextValue;
    if (options.icon) {
      this.iconPath = options.icon;
    }
  }
}

/** Plan step index carried by step items (read by approve/reject handlers). */
export const stepIndexFor = new WeakMap<PlanTreeItem, number>();

function jsonEntry(key: string, value: unknown): PlanTreeItem {
  if (isRecord(value)) {
    const entries = Object.entries(value);
    const children = entries.map(([childKey, childValue]) => jsonEntry(childKey, childValue));
    return new PlanTreeItem(
      `${key} (${entries.length})`,
      children.length > 0 ? children : [new PlanTreeItem("(empty object)")],
    );
  }
  if (Array.isArray(value)) {
    const children = value.map((childValue, index) => jsonEntry(String(index), childValue));
    return new PlanTreeItem(
      `${key} (${value.length})`,
      children.length > 0 ? children : [new PlanTreeItem("(empty array)")],
    );
  }
  return new PlanTreeItem(`${key}: ${String(value)}`);
}

function stepItem(step: unknown, index: number): PlanTreeItem {
  const record = isRecord(step) ? step : {};
  const title = typeof record["title"] === "string" && record["title"] ? record["title"] : "unnamed step";
  const status = typeof record["status"] === "string" ? record["status"] : "";
  const summaryText = typeof record["summary"] === "string" ? record["summary"] : "";
  const children: PlanTreeItem[] = [];
  if (summaryText) {
    children.push(new PlanTreeItem(`summary: ${summaryText}`));
  }
  if (isRecord(record["approval"])) {
    const decision = typeof record["approval"]["decision"] === "string" ? record["approval"]["decision"] : "?";
    const note = typeof record["approval"]["note"] === "string" && record["approval"]["note"]
      ? ` — ${record["approval"]["note"]}`
      : "";
    children.push(new PlanTreeItem(`approval: ${decision}${note}`));
  }
  const item = new PlanTreeItem(`Step ${index}: ${title}`, children, {
    description: status,
    tooltip: summaryText,
    contextValue: "planStep",
    icon: new vscode.ThemeIcon(stepStatusIcon(status)),
  });
  stepIndexFor.set(item, index);
  return item;
}

/** Renders the whole plan document (as returned by the API) into tree nodes. */
export function buildPlanTree(plan: unknown): PlanTreeItem[] {
  if (plan === null || plan === undefined) {
    return [new PlanTreeItem("No plan yet", [], { description: "job is still PLANNING" })];
  }
  if (!isRecord(plan)) {
    return [new PlanTreeItem(String(plan))];
  }
  const items: PlanTreeItem[] = [];
  for (const [key, value] of Object.entries(plan)) {
    if (key === "steps" && Array.isArray(value)) {
      const stepItems = value.map((step, index) => stepItem(step, index));
      items.push(new PlanTreeItem(`steps (${stepItems.length})`, stepItems));
      continue;
    }
    items.push(jsonEntry(key, value));
  }
  return items.length > 0 ? items : [new PlanTreeItem("(empty plan object)")];
}

export class PlanProvider implements vscode.TreeDataProvider<PlanTreeItem> {
  private readonly emitter = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.emitter.event;

  private items: PlanTreeItem[] = [new PlanTreeItem("Select a job to see its plan")];

  setPlan(plan: unknown): void {
    this.items = buildPlanTree(plan);
    this.emitter.fire();
  }

  setMessage(message: string): void {
    this.items = [new PlanTreeItem(message)];
    this.emitter.fire();
  }

  getTreeItem(element: PlanTreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: PlanTreeItem): PlanTreeItem[] {
    return element ? element.children ?? [] : this.items;
  }
}
