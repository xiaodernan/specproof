/**
 * Extension host: sidebar views, commands, status bar and polling.
 * All HTTP work lives in src/client.ts (pure, unit-tested separately);
 * this file only wires VS Code UI on top of it.
 */

import * as vscode from "vscode";
import {
  AgentApiClient,
  describeAgentError,
  firstActiveJob,
  type ApprovalDecision,
  type ApprovalTarget,
} from "./client";
import { JobTreeItem, JobsProvider, statusIcon } from "./jobsProvider";
import { PlanProvider, stepIndexFor, type PlanTreeItem } from "./planProvider";
import { DIFF_SCHEME, DiffDocumentProvider, DiffProvider, DiffTreeItem, diffUri } from "./diffProvider";

const CONFIG_SECTION = "specproofAgent";

function buildClient(): AgentApiClient {
  const config = vscode.workspace.getConfiguration(CONFIG_SECTION);
  return new AgentApiClient({
    baseUrl: config.get<string>("apiBaseUrl", "http://127.0.0.1:8000"),
    apiKey: config.get<string>("apiKey", ""),
  });
}

export class ConsoleExtension implements vscode.Disposable {
  client = buildClient();
  private currentJobId: string | null = null;
  private tasksView: vscode.TreeView<JobTreeItem> | null = null;
  private pollTimer: NodeJS.Timeout | undefined;
  private pollInFlight = false;

  readonly jobsProvider = new JobsProvider();
  readonly planProvider = new PlanProvider();
  readonly diffProvider = new DiffProvider();
  private readonly statusBar: vscode.StatusBarItem;

  constructor() {
    this.statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 95);
    this.statusBar.command = "specproofAgent.showStatus";
    this.statusBar.hide();
  }

  dispose(): void {
    this.stopPolling();
    this.statusBar.dispose();
  }

  setTasksView(view: vscode.TreeView<JobTreeItem>): void {
    this.tasksView = view;
  }

  // ── polling ──────────────────────────────────────────────────────────────

  startPolling(): void {
    this.stopPolling();
    const config = vscode.workspace.getConfiguration(CONFIG_SECTION);
    const seconds = config.get<number>("pollIntervalSeconds", 5);
    this.pollTimer = setInterval(() => {
      void this.pollTick();
    }, Math.max(1, seconds) * 1000);
  }

  private stopPolling(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = undefined;
    }
  }

  private async pollTick(): Promise<void> {
    if (this.pollInFlight) {
      return;
    }
    if (!this.tasksView || !this.tasksView.visible) {
      return;
    }
    this.pollInFlight = true;
    try {
      await this.refreshTasks(false);
    } catch {
      // transient failures are surfaced by the next manual refresh
    } finally {
      this.pollInFlight = false;
    }
  }

  // ── refresh pipeline ─────────────────────────────────────────────────────

  async refreshTasks(showErrors: boolean): Promise<void> {
    try {
      const list = await this.client.listJobs();
      const jobs = list.jobs;
      if (!this.currentJobId || !jobs.some((job) => job.id === this.currentJobId)) {
        const pick = firstActiveJob(jobs) ?? jobs[0] ?? null;
        this.currentJobId = pick ? pick.id : null;
      }
      this.jobsProvider.setData(jobs, this.currentJobId);
      await this.refreshPlan();
      await this.refreshDiff();
      this.updateStatusBar();
    } catch (error) {
      if (showErrors) {
        vscode.window.showErrorMessage(`SpecProof agent API unreachable: ${describeAgentError(error)}`);
      }
      throw error;
    }
  }

  async refreshPlan(): Promise<void> {
    if (!this.currentJobId) {
      this.planProvider.setMessage("Select a job to see its plan");
      return;
    }
    try {
      const detail = await this.client.getJob(this.currentJobId);
      this.planProvider.setPlan(detail.job.plan);
    } catch (error) {
      this.planProvider.setMessage(describeAgentError(error));
    }
  }

  async refreshDiff(): Promise<void> {
    if (!this.currentJobId) {
      this.diffProvider.setMessage("Select a job to see changed files");
      return;
    }
    try {
      const response = await this.client.getDiff(this.currentJobId);
      this.diffProvider.setFiles(response.files, this.currentJobId);
    } catch (error) {
      this.diffProvider.setMessage(describeAgentError(error));
    }
  }

  async refreshAll(): Promise<void> {
    await this.refreshTasks(false);
  }

  // ── status bar ───────────────────────────────────────────────────────────

  private updateStatusBar(): void {
    const job = this.jobsProvider
      .getJobs()
      .find((candidate) => candidate.id === this.currentJobId);
    if (!job) {
      this.statusBar.hide();
      return;
    }
    this.statusBar.text = `$(${statusIcon(job.status)}) SpecProof: ${job.status} · ${job.task_name}`;
    this.statusBar.tooltip = [
      `Job: ${job.id}`,
      `Repo: ${job.repo_path}`,
      `Events: ${job.events_count} · Approvals: ${job.approvals_count}`,
      `Updated: ${job.updated_at}`,
    ].join("\n");
    this.statusBar.show();
  }

  // ── commands ─────────────────────────────────────────────────────────────

  async setCurrentJob(jobId: string): Promise<void> {
    this.currentJobId = jobId;
    await this.refreshAll();
  }

  async createJob(): Promise<void> {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    const repoPath = await vscode.window.showInputBox({
      title: "Create agent job",
      prompt: "Repository path (leave empty, with an empty spec below, to run the bundled demo task)",
      value: workspaceFolder?.uri.fsPath ?? "",
      ignoreFocusOut: true,
    });
    if (repoPath === undefined) {
      return;
    }
    const specText = await vscode.window.showInputBox({
      title: "Create agent job",
      prompt: "Specification text",
      ignoreFocusOut: true,
    });
    if (specText === undefined) {
      return;
    }
    const trimmedRepo = repoPath.trim();
    const trimmedSpec = specText.trim();
    const autoStart = trimmedRepo === "" && trimmedSpec === "";
    let taskName: string | undefined;
    if (!autoStart) {
      const entered = await vscode.window.showInputBox({
        title: "Create agent job",
        prompt: "Task name (optional)",
        ignoreFocusOut: true,
      });
      if (entered === undefined) {
        return;
      }
      taskName = entered.trim() || undefined;
    }
    try {
      const response = await this.client.createJob({
        repoPath: trimmedRepo,
        specText: trimmedSpec,
        taskName,
        autoStart,
      });
      this.currentJobId = response.job_id;
      await this.refreshAll();
      vscode.window.showInformationMessage(
        `Created agent job ${response.job_id.slice(0, 8)} → ${response.status}`,
      );
    } catch (error) {
      vscode.window.showErrorMessage(describeAgentError(error));
    }
  }

  async approve(target: ApprovalTarget, decision: ApprovalDecision, jobId?: string, stepIndex?: number): Promise<void> {
    const id = jobId ?? this.currentJobId;
    if (!id) {
      vscode.window.showWarningMessage("Select an agent job first.");
      return;
    }
    const note = await vscode.window.showInputBox({
      prompt: `Note for ${decision} on ${target} (optional)`,
      ignoreFocusOut: true,
    });
    if (note === undefined) {
      return;
    }
    try {
      const response = await this.client.approveJob(id, {
        decision,
        target,
        note: note.trim() || undefined,
        stepIndex,
      });
      vscode.window.showInformationMessage(
        `${decision} ${target} on ${id.slice(0, 8)} → ${response.job.status}`,
      );
      await this.refreshAll();
    } catch (error) {
      vscode.window.showErrorMessage(describeAgentError(error));
    }
  }

  async approveStep(item: PlanTreeItem, decision: ApprovalDecision): Promise<void> {
    const stepIndex = stepIndexFor.get(item);
    if (stepIndex === undefined) {
      vscode.window.showWarningMessage("Could not resolve the plan step index.");
      return;
    }
    await this.approve("step", decision, undefined, stepIndex);
  }

  async cancelJob(jobId?: string): Promise<void> {
    const id = jobId ?? this.currentJobId;
    if (!id) {
      vscode.window.showWarningMessage("Select an agent job first.");
      return;
    }
    const choice = await vscode.window.showWarningMessage(
      `Cancel agent job ${id.slice(0, 8)}?`,
      { modal: true },
      "Yes, Cancel Job",
    );
    if (choice !== "Yes, Cancel Job") {
      return;
    }
    try {
      const response = await this.client.cancelJob(id);
      vscode.window.showInformationMessage(`Job ${id.slice(0, 8)} → ${response.status}`);
      await this.refreshAll();
    } catch (error) {
      vscode.window.showErrorMessage(describeAgentError(error));
    }
  }

  async openDiff(jobId: string, filePath: string): Promise<void> {
    const uri = diffUri(jobId, filePath);
    const document = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(document, { preview: true });
  }

  showStatus(): void {
    if (!this.currentJobId) {
      vscode.window.showInformationMessage("No current agent job — pick one in the Agent Tasks view.");
      return;
    }
    void vscode.commands.executeCommand("specproofAgent.tasks.focus");
  }
}

export function activate(context: vscode.ExtensionContext): void {
  const ext = new ConsoleExtension();

  const tasksView = vscode.window.createTreeView("specproofAgent.tasks", {
    treeDataProvider: ext.jobsProvider,
  });
  ext.setTasksView(tasksView);
  context.subscriptions.push(
    tasksView,
    vscode.window.createTreeView("specproofAgent.plan", { treeDataProvider: ext.planProvider }),
    vscode.window.createTreeView("specproofAgent.diff", { treeDataProvider: ext.diffProvider }),
    vscode.workspace.registerTextDocumentContentProvider(
      DIFF_SCHEME,
      new DiffDocumentProvider(() => ext.client),
    ),
  );

  const register = (name: string, handler: (...args: any[]) => unknown): void => {
    context.subscriptions.push(vscode.commands.registerCommand(name, handler));
  };

  /**
   * View-item context menus send the tree item itself as the first argument,
   * while item clicks send the TreeItem.command arguments (a plain job id).
   * Accept both shapes so approve/cancel/set-current work from either path.
   */
  const jobIdOf = (arg: unknown): string | undefined => {
    if (typeof arg === "string") {
      return arg;
    }
    if (arg instanceof JobTreeItem) {
      return arg.id;
    }
    return undefined;
  };

  register("specproofAgent.refreshTasks", () => ext.refreshTasks(true));
  register("specproofAgent.refreshDiff", () => ext.refreshDiff());
  register("specproofAgent.setCurrentJob", (arg: unknown) => {
    const id = jobIdOf(arg);
    if (id) {
      void ext.setCurrentJob(id);
    }
  });
  register("specproofAgent.createJob", () => ext.createJob());
  register("specproofAgent.approvePlan", (arg: unknown) => void ext.approve("plan", "approve", jobIdOf(arg)));
  register("specproofAgent.rejectPlan", (arg: unknown) => void ext.approve("plan", "reject", jobIdOf(arg)));
  register("specproofAgent.approveGate", (arg: unknown) => void ext.approve("gate", "approve", jobIdOf(arg)));
  register("specproofAgent.rejectGate", (arg: unknown) => void ext.approve("gate", "reject", jobIdOf(arg)));
  register("specproofAgent.cancelJob", (arg: unknown) => void ext.cancelJob(jobIdOf(arg)));
  register("specproofAgent.openDiff", (...args: unknown[]) => {
    const [first, second] = args;
    if (typeof first === "string" && typeof second === "string") {
      void ext.openDiff(first, second);
      return;
    }
    if (first instanceof DiffTreeItem && first.jobId && first.filePath) {
      void ext.openDiff(first.jobId, first.filePath);
    }
  });
  register("specproofAgent.showStatus", () => ext.showStatus());
  register("specproofAgent.approveStep", (item: PlanTreeItem) => ext.approveStep(item, "approve"));
  register("specproofAgent.rejectStep", (item: PlanTreeItem) => ext.approveStep(item, "reject"));

  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (!event.affectsConfiguration(CONFIG_SECTION)) {
        return;
      }
      ext.client = buildClient();
      ext.startPolling();
      void ext.refreshAll();
    }),
    ext,
  );

  ext.startPolling();
  void ext.refreshTasks(true);
}
