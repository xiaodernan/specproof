/**
 * Changed Files sidebar (GET /agent/jobs/{id}/diff) plus a virtual text
 * document that renders one file of the change bundle as a unified diff.
 */

import * as vscode from "vscode";
import { describeAgentError, type AgentApiClient, type DiffFile } from "./client";
import { renderDiffFile } from "./diffText";

export const DIFF_SCHEME = "specproof-diff";

/** URI for the virtual diff document of one file inside a job's bundle. */
export function diffUri(jobId: string, filePath: string): vscode.Uri {
  return vscode.Uri.from({
    scheme: DIFF_SCHEME,
    path: `/${jobId}/${encodeURIComponent(filePath)}`,
  });
}

export function parseDiffUri(uri: vscode.Uri): { jobId: string; filePath: string } | null {
  const parts = uri.path.split("/");
  if (parts.length < 3) {
    return null;
  }
  const jobId = parts[1];
  const filePath = decodeURIComponent(parts.slice(2).join("/"));
  return { jobId, filePath };
}

function fileIcon(status: string): string {
  if (status === "added") return "diff-added";
  if (status === "deleted") return "diff-removed";
  return "diff-modified";
}

export class DiffTreeItem extends vscode.TreeItem {
  constructor(
    label: string,
    public readonly children?: DiffTreeItem[],
    options: { description?: string; tooltip?: string; contextValue?: string; icon?: vscode.ThemeIcon; command?: vscode.Command } = {},
    public readonly jobId?: string,
    public readonly filePath?: string,
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
    if (options.command) {
      this.command = options.command;
    }
  }
}

export class DiffProvider implements vscode.TreeDataProvider<DiffTreeItem> {
  private readonly emitter = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.emitter.event;

  private items: DiffTreeItem[] = [new DiffTreeItem("Select a job to see changed files")];

  setFiles(files: DiffFile[], jobId: string): void {
    if (files.length === 0) {
      this.items = [new DiffTreeItem("No files in the change bundle yet")];
    } else {
      this.items = files.map((file) => {
        const hunks = file.hunks.map(
          (hunk) =>
            new DiffTreeItem(
              `@@ -${hunk.old_start},${hunk.old_count} +${hunk.new_start},${hunk.new_count} @@`,
              undefined,
              { description: `${hunk.lines.length} line(s)` },
            ),
        );
        const basename = file.path.split(/[\\/]/).pop() ?? file.path;
        return new DiffTreeItem(basename, hunks, {
          description: `${file.status} +${file.insertions} -${file.deletions}`,
          tooltip: file.path,
          contextValue: "diffFile",
          icon: new vscode.ThemeIcon(fileIcon(file.status)),
          command: {
            command: "specproofAgent.openDiff",
            title: "Open Diff",
            arguments: [jobId, file.path],
          },
        }, jobId, file.path);
      });
    }
    this.emitter.fire();
  }

  setMessage(message: string): void {
    this.items = [new DiffTreeItem(message)];
    this.emitter.fire();
  }

  getTreeItem(element: DiffTreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: DiffTreeItem): DiffTreeItem[] {
    return element ? element.children ?? [] : this.items;
  }
}

export class DiffDocumentProvider implements vscode.TextDocumentContentProvider {
  private readonly emitter = new vscode.EventEmitter<vscode.Uri>();
  readonly onDidChange = this.emitter.event;

  constructor(private readonly getClient: () => AgentApiClient) {}

  async provideTextDocumentContent(uri: vscode.Uri): Promise<string> {
    const parsed = parseDiffUri(uri);
    if (!parsed) {
      return "Invalid SpecProof diff URI";
    }
    try {
      const response = await this.getClient().getDiff(parsed.jobId);
      const file = response.files.find((candidate) => candidate.path === parsed.filePath);
      if (!file) {
        return `File ${parsed.filePath} is not in the change bundle of job ${parsed.jobId}`;
      }
      return renderDiffFile(file);
    } catch (error) {
      return describeAgentError(error);
    }
  }
}
