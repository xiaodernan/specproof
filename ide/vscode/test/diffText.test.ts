/**
 * Unit tests for the pure diff text renderer (src/diffText.ts).
 * Runs on plain Node — no VS Code host involved.
 */

import { describe, expect, it } from "vitest";
import {
  renderDiffDocument,
  renderDiffFile,
  renderDiffHunkHeader,
  renderDiffLine,
} from "../src/diffText";
import type { DiffFile, DiffResponse } from "../src/client";

describe("renderDiffLine", () => {
  it("renders added lines with a + sign and a padded new line number", () => {
    const text = renderDiffLine({ type: "add", old_no: null, new_no: 7, text: "x = 2" });
    expect(text).toBe("+     7 | x = 2");
  });

  it("renders deleted lines with a - sign and a padded old line number", () => {
    const text = renderDiffLine({ type: "del", old_no: 3, new_no: null, text: "x = 1" });
    expect(text).toBe("-    3  | x = 1");
  });

  it("renders context lines with both line numbers", () => {
    const text = renderDiffLine({ type: "context", old_no: 10, new_no: 12, text: "return x" });
    expect(text).toBe("    10   12 | return x");
  });
});

describe("renderDiffHunkHeader", () => {
  it("renders GNU-style unified hunk headers", () => {
    const header = renderDiffHunkHeader({
      old_start: 3, old_count: 2, new_start: 5, new_count: 4, lines: [],
    });
    expect(header).toBe("@@ -3,2 +5,4 @@");
  });
});

describe("renderDiffFile", () => {
  const file: DiffFile = {
    path: "src/calc.py",
    status: "modified",
    hunks: [
      {
        old_start: 1, old_count: 1, new_start: 1, new_count: 1,
        lines: [
          { type: "del", old_no: 1, new_no: null, text: "x = 1" },
          { type: "add", old_no: null, new_no: 1, text: "x = 2" },
        ],
      },
    ],
    insertions: 1,
    deletions: 1,
  };

  it("renders the file header, hunk header and lines", () => {
    const text = renderDiffFile(file);
    expect(text).toContain("== src/calc.py (modified) +1 -1");
    expect(text).toContain("@@ -1,1 +1,1 @@");
    expect(text).toContain("-    1  | x = 1");
    expect(text).toContain("+     1 | x = 2");
  });

  it("notes files whose hunks are empty", () => {
    const text = renderDiffFile({ ...file, hunks: [] });
    expect(text).toContain("(no differing lines)");
  });
});

describe("renderDiffDocument", () => {
  it("renders aggregate stats followed by every file", () => {
    const response: DiffResponse = {
      job_id: "job-1",
      mode: "unified",
      stats: { files_changed: 1, insertions: 1, deletions: 1 },
      files: [
        {
          path: "src/calc.py",
          status: "modified",
          hunks: [],
          insertions: 1,
          deletions: 1,
        },
      ],
      generated_at: "2026-08-18T00:03:00+00:00",
    };
    const text = renderDiffDocument(response);
    expect(text).toContain("Change bundle for job job-1 — 1 file(s), +1 -1");
    expect(text).toContain("== src/calc.py (modified) +1 -1");
  });
});
