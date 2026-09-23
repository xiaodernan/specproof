import { describe, expect, it } from "vitest";
import { GLOSSARY, glossaryEntry } from "../glossary";

// The glossary is the single source of truth for 需求矩阵 / 契约 / 风险发现 /
// 证据包 / 合并证书 / 开发助手 across the Guide page and every inline <Term>.
// These tests lock the invariants the UI relies on.

describe("glossary", () => {
  it("exposes every entry under its own id, with no duplicate ids", () => {
    const ids = GLOSSARY.map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const entry of GLOSSARY) {
      expect(glossaryEntry(entry.id)).toBe(entry);
    }
  });

  it("keeps the six terms the Guide glossary already published", () => {
    // These ids were rendered verbatim by pages/Guide.tsx before the shared
    // glossary existed; dropping one would silently shorten the guide.
    const ids = GLOSSARY.map((e) => e.id);
    for (const required of ["matrix", "contract", "finding", "capsule", "certificate", "craft"]) {
      expect(ids).toContain(required);
    }
  });

  it("gives every entry a label and a definition, and never an empty one", () => {
    for (const entry of GLOSSARY) {
      expect(entry.label.trim().length).toBeGreaterThan(0);
      expect(entry.definition.trim().length).toBeGreaterThan(0);
    }
  });

  it("returns undefined for an unknown id instead of inventing an entry", () => {
    // The UI passes this straight through — a missing explanation is honest,
    // a fabricated one would mislead.
    expect(glossaryEntry("nope")).toBeUndefined();
    expect(glossaryEntry("")).toBeUndefined();
  });
});
