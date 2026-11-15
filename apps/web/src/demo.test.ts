import { describe, expect, it } from "vitest";
import {
  DEMO_VERIFY_REPO_NOTE,
  DEMO_VERIFY_PREPARE_NOTE,
  DEMO_VERIFY_ABS_PATH_NOTE,
  demoAgentSample,
  demoVerifyNotes,
} from "./demo";

// Guide renders DEMO_VERIFY_ABS_PATH_NOTE inline; NewVerification renders the
// composed full note. Lock the composition so editing one sentence can never
// silently drop the other from the UI (the old code split() on "; " at render
// time and fell back to "" — an invisible regression).
describe("demo first-run note", () => {
  it("composes the full note from the two named sentences", () => {
    expect(DEMO_VERIFY_REPO_NOTE).toBe(DEMO_VERIFY_PREPARE_NOTE + "; " + DEMO_VERIFY_ABS_PATH_NOTE);
  });

  it("keeps the prepare hint pointing at both CLI and script", () => {
    expect(DEMO_VERIFY_PREPARE_NOTE).toContain("specproof demo");
    expect(DEMO_VERIFY_PREPARE_NOTE).toContain("prepare_demo_repo.ps1");
  });

  it("produces a complete English first-run pair, with zero Chinese residue", () => {
    const notes = demoVerifyNotes("en");
    expect(notes.prepare).toContain("specproof demo");
    expect(notes.prepare).toContain("prepare_demo_repo.ps1");
    expect(notes.absPath).toContain("absolute path");
    expect(notes.repo).toBe(notes.prepare + "; " + notes.absPath);
    expect(notes.prepare).not.toMatch(/[一-鿿]/);
    expect(notes.absPath).not.toMatch(/[一-鿿]/);
    const agent = demoAgentSample("en");
    expect(agent.task_name).toBe("Fix the double function");
    expect(agent.spec_text).toContain("x * 2");
    expect(agent.spec_text).not.toMatch(/[一-鿿]/);
  });

  it("keeps the absolute-path follow-up non-empty (never dropped)", () => {
    expect(DEMO_VERIFY_ABS_PATH_NOTE.trim().length).toBeGreaterThan(0);
    expect(DEMO_VERIFY_ABS_PATH_NOTE).toContain("绝对路径");
  });
});
