import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Term } from "../Term";
import { glossaryEntry } from "../glossary";

// Inline glossary term (roadmap Phase 3.3). The visible text is the page's own
// wording; the definition lives in a tooltip. Unknown ids must pass through
// untouched — never a guessed definition.

describe("Term", () => {
  it("renders the caller's wording and keeps the definition out of the prose", () => {
    render(<Term id="capsule">证据包</Term>);

    const text = screen.getByText("证据包", { selector: ".ui-term-text" });
    expect(text).toBeTruthy();
    // The definition is present for assistive tech / hover but the visible
    // prose stays the page's own short label.
    const entry = glossaryEntry("capsule")!;
    expect(document.body.textContent).toContain(entry.definition);
    expect(text.className).toBe("ui-term-text");
  });

  it("wires the tooltip to the trigger for screen readers and keyboard focus", () => {
    render(<Term id="contract">契约</Term>);

    // The trigger text and the tooltip label are the same word, so scope to
    // the affordance span rather than matching on text alone.
    const trigger = screen.getByText("契约", { selector: ".ui-term-text" });
    // Tooltip clones the child and adds aria-describedby pointing at the bubble.
    const describedBy = trigger.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy!)?.getAttribute("role")).toBe("tooltip");
    // Reachable without a mouse (the CSS reveals on :focus-within).
    expect(trigger.getAttribute("tabindex")).toBe("0");
  });

  it("surfaces the English original alongside the definition, for audit", () => {
    render(<Term id="certificate">合并证书</Term>);

    const en = document.querySelector(".ui-term-en");
    expect(en?.textContent).toBe(glossaryEntry("certificate")!.en);
  });

  it("passes unknown ids through verbatim instead of inventing a definition", () => {
    render(<Term id="not-a-real-term">某个词</Term>);

    expect(screen.getByText("某个词")).toBeTruthy();
    // No tooltip wrapper, no term affordance, no fabricated copy.
    expect(document.querySelector(".ui-term")).toBeNull();
    expect(document.querySelector(".ui-tooltip")).toBeNull();
  });
});
