/**
 * Tree view provider for the Agent Tasks sidebar (GET /agent/jobs).
 */

import * as vscode from "vscode";
import type { AgentJobStatus, AgentJobSummary } from "./client";

const STATUS_ICONS: Record<string, string> = {
  PLANNING: "circle-outline",
  AWAITING_APPROVAL: "question",
  EXECUTING: "sync~spin",
  COMPLETED: "check",
  FAILED: "error",
  CANCELLED: "close",
};

/** Codicon name for a console status (shared with the status bar). */
export function statusIcon(status: AgentJobStatus): string {
  return STATUS_ICONS[status] ?? "circle-outline";
}

export class JobTreeItem extends vscode.TreeItem {
  constructor(job: AgentJobSummary, isCurrent: boolean) {
    super(job.task_name, vscode.TreeItemCollapsibleState.None);
    this.id = job.id;
    this.description = `${job.status} · ${job.plan_steps} step(s)`;
    this.tooltip = [
      `id: ${job.id}`,
      `repo: ${job.repo_path}`,
      `events: ${job.events_count} · approvals: ${job.approvals_count}`,
      `updated: ${job.updated_at}`,
    ].join("\n");
    this.iconPath = new vscode.ThemeIcon(statusIcon(job.status));
    this.contextValue = isCurrent ? "currentJob" : "job";
    this.command = {
      command: "specproofAgent.setCurrentJob",
      title: "Set as Current Job",
      arguments: [job.id],
    };
  }
}

export class JobsProvider implements vscode.TreeDataProvider<JobTreeItem> {
  private readonly emitter = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.emitter.event;

  private jobs: AgentJobSummary[] = [];
  private currentJobId: string | null = null;

  getJobs(): readonly AgentJobSummary[] {
    return this.jobs;
  }

  getCurrentJobId(): string | null {
    return this.currentJobId;
  }

  setData(jobs: AgentJobSummary[], currentJobId: string | null): void {
    this.jobs = jobs;
    this.currentJobId = currentJobId;
    this.emitter.fire();
  }

  getTreeItem(element: JobTreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(_element?: JobTreeItem): JobTreeItem[] {
    return this.jobs.map((job) => new JobTreeItem(job, job.id === this.currentJobId));
  }
}
