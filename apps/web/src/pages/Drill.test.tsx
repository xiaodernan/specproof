import { describe, expect, it, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import Drill from "./Drill";
import { DRILL_QUESTIONS, DRILL_TOTAL } from "./drillQuestions";
import { DRILL_STORE_KEY } from "./drill.copy";

// The drill runs entirely on the client; jsdom supplies localStorage.
// Each test starts with a clean slate and zh pinned by src/test-setup.ts.

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem("specproof_locale", "zh");
});

describe("Verify Drill", () => {
  it("renders the idle screen with the seal ladder and stats", () => {
    render(<Drill />);
    expect(screen.getByRole("button", { name: "开始练功" })).toBeTruthy();
    expect(screen.getByText("见习验收官")).toBeTruthy();
    expect(screen.getByText("铁证验收官")).toBeTruthy();
  });

  it("locks the answer on first pick and speaks the teacher's note", () => {
    render(<Drill />);
    fireEvent.click(screen.getByRole("button", { name: "开始练功" }));
    const q = DRILL_QUESTIONS[0];
    const correct = q.choices.zh[q.answer];
    fireEvent.click(screen.getByRole("button", { name: correct }));
    expect(screen.getByText("铁证如山")).toBeTruthy();
    // locked once picked — the correct choice stays but the buttons are disabled
    expect((screen.getByRole("button", { name: correct }) as HTMLButtonElement).disabled).toBe(true);
    // teacher note fires for the right answer too
    expect(screen.getByText(new RegExp(q.teach.zh.slice(0, 16)))).toBeTruthy();
  });

  it("shows a refusal when Enter is pressed before any answer", () => {
    render(<Drill />);
    fireEvent.click(screen.getByRole("button", { name: "开始练功" }));
    fireEvent.keyDown(window, { key: "Enter" });
    expect(screen.getByText("先给一个答案再进下一题")).toBeTruthy();
  });

  it("plays a full run and persists the best score", () => {
    render(<Drill />);
    fireEvent.click(screen.getByRole("button", { name: "开始练功" }));
    for (let i = 0; i < DRILL_TOTAL; i++) {
      const q = DRILL_QUESTIONS[i];
      fireEvent.click(screen.getByRole("button", { name: q.choices.zh[q.answer] }));
      const isLast = i + 1 === DRILL_TOTAL;
      fireEvent.click(screen.getByRole("button", { name: isLast ? "揭晓成绩" : "下一题" }));
    }
    expect(screen.getByText("12 / 12")).toBeTruthy();
    expect(screen.getByText("铁证验收官")).toBeTruthy();
    expect(screen.getByText("满分。一字不改地过关。")).toBeTruthy();
    const stored = JSON.parse(window.localStorage.getItem(DRILL_STORE_KEY) ?? "{}");
    expect(stored.best).toBe(12);
    expect(stored.runs).toBe(1);
  });

  it("records a mixed run honestly and shows the missed-question recap", () => {
    render(<Drill />);
    fireEvent.click(screen.getByRole("button", { name: "开始练功" }));
    let wrongUsed = 0;
    for (let i = 0; i < DRILL_TOTAL; i++) {
      const q = DRILL_QUESTIONS[i];
      // deliberately miss the first three, ace the rest
      const choice = wrongUsed < 3
        ? q.choices.zh[(q.answer + 1) % q.choices.zh.length]
        : q.choices.zh[q.answer];
      if (wrongUsed < 3) wrongUsed += 1;
      fireEvent.click(screen.getByRole("button", { name: choice }));
      const isLast = i + 1 === DRILL_TOTAL;
      fireEvent.click(screen.getByRole("button", { name: isLast ? "揭晓成绩" : "下一题" }));
    }
    expect(screen.getByText("9 / 12")).toBeTruthy();
    expect(screen.getByText(/回炉的那几题/)).toBeTruthy();
    const stored = JSON.parse(window.localStorage.getItem(DRILL_STORE_KEY) ?? "{}");
    expect(stored.best).toBe(9);
  });
});
