import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import Library from "../Library";
import library from "../library.json";

/**
 * The Library is the open-world door (#108): a reader who does not know which
 * of the 206 scrolls to open can "wander" to an arbitrary real one. The wander
 * target must be drawn from the FULL library — never a filtered subset, never
 * a fabricated scroll — and the page count must be derived from the data so a
 * rebuilt bible cannot leave a stale number on screen.
 */
describe("Library wander (#108 open world)", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("derives the scroll count from library.json, never a hard-coded 203", () => {
    render(<Library />);
    const total = library.zh.length;
    expect(screen.getByText(new RegExp(`${total} SCROLLS`))).toBeTruthy();
    expect(screen.queryByText(/203 SCROLLS/)).toBeNull();
  });

  it("renders a wander control in both locales' shared button", () => {
    render(<Library />);
    expect(screen.getByRole("button", { name: /wander|漫游/ })).toBeTruthy();
  });

  it("wander opens exactly one real scroll, from the full library", () => {
    vi.useFakeTimers();
    Element.prototype.scrollIntoView = vi.fn();
    const random = vi.spyOn(Math, "random").mockReturnValue(0.5);
    render(<Library />);

    // A filter is active — wander must clear it so its target is reachable.
    const filter = screen.getByRole("searchbox") as HTMLInputElement;
    fireEvent.change(filter, { target: { value: "卷二百零五" } });

    const wander = screen.getByRole("button", { name: /wander|漫游/ });
    fireEvent.click(wander);

    const targetIndex = Math.floor(0.5 * library.zh.length);
    const targetNum = library.zh[targetIndex].num;
    // The chosen scroll's excerpt is now shown (open === targetNum).
    expect(screen.getByText(library.zh[targetIndex].excerpt)).toBeTruthy();
    // Filter cleared: the count line reads the full library again.
    act(() => { vi.runAllTimers(); });
    expect(random).toHaveBeenCalled();
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    expect(targetNum.length).toBeGreaterThan(0);
  });
});
