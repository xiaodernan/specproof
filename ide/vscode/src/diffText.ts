/**
 * Pure text rendering for the agent console structured diff endpoint.
 * No "vscode" imports — unit-testable with vitest on plain Node.
 */

import type { DiffFile, DiffHunk, DiffLine, DiffResponse } from "./client";

/** One diff line as "+  old new | text", "-  ..." or "   ...". */
export function renderDiffLine(line: DiffLine): string {
  const sign = line.type === "add" ? "+" : line.type === "del" ? "-" : " ";
  const oldNo = line.old_no === null ? "" : String(line.old_no).padStart(4);
  const newNo = line.new_no === null ? "" : String(line.new_no).padStart(4);
  return `${sign} ${oldNo} ${newNo} | ${line.text}`;
}

/** Unified hunk header in GNU style: "@@ -old_start,old_count +new_start,new_count @@". */
export function renderDiffHunkHeader(hunk: DiffHunk): string {
  return `@@ -${hunk.old_start},${hunk.old_count} +${hunk.new_start},${hunk.new_count} @@`;
}

/** Header plus all hunks of one changed file. */
export function renderDiffFile(file: DiffFile): string {
  const header =
    `== ${file.path} (${file.status}) +${file.insertions} -${file.deletions}`;
  if (file.hunks.length === 0) {
    return `${header}\n(no differing lines)`;
  }
  const body = file.hunks
    .map((hunk) => `${renderDiffHunkHeader(hunk)}\n${hunk.lines.map(renderDiffLine).join("\n")}`)
    .join("\n");
  return `${header}\n${body}`;
}

/** Full change bundle rendered as one plain-text document. */
export function renderDiffDocument(response: DiffResponse): string {
  const head = [
    `Change bundle for job ${response.job_id} — ${response.stats.files_changed} file(s), +${response.stats.insertions} -${response.stats.deletions}`,
    `mode: ${response.mode} · generated at: ${response.generated_at}`,
    "",
  ];
  const sections = response.files.map((file) => renderDiffFile(file) + "\n");
  return head.concat(sections).join("\n");
}
