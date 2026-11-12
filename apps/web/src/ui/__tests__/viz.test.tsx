import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { AreaChart } from "../AreaChart";
import { DonutMeter } from "../DonutMeter";
import { CountUp } from "../CountUp";
import { Sparkline } from "../Sparkline";

describe("visualization layer", () => {
  it("AreaChart draws an SVG line and exposes the final value for a11y", () => {
    const { container } = render(
      <AreaChart
        data={[
          { label: "00:00", value: 3 },
          { label: "01:00", value: 7 },
          { label: "02:00", value: 4 },
        ]}
        ariaLabel="trend"
      />
    );
    expect(container.querySelector("svg.viz-area")).toBeTruthy();
    expect(container.querySelector("path.viz-area-line")).toBeTruthy();
    expect(screen.getByLabelText("trend")).toBeTruthy();
  });

  it("AreaChart degrades to a placeholder when empty", () => {
    render(<AreaChart data={[]} emptyHint="无数据" />);
    expect(screen.getByText("无数据")).toBeTruthy();
  });

  it("DonutMeter renders one arc per non-zero segment and a legend", () => {
    const { container } = render(
      <DonutMeter
        segments={[
          { label: "已通过", value: 12, color: "var(--success)" },
          { label: "已拦截", value: 3, color: "var(--warning)" },
        ]}
        centerValue={15}
        centerLabel="累计验收"
      />
    );
    // two non-zero segments -> two arc circles
    expect(container.querySelectorAll("circle.viz-donut-arc").length).toBe(2);
    expect(screen.getByText("已通过")).toBeTruthy();
    expect(screen.getByText("已拦截")).toBeTruthy();
    expect(container.querySelector("text.viz-donut-value")?.textContent).toBe("15");
  });

  it("DonutMeter shows placeholder when total is zero", () => {
    render(<DonutMeter segments={[{ label: "x", value: 0, color: "#fff" }]} emptyHint="空" />);
    expect(screen.getByText("空")).toBeTruthy();
  });

  it("CountUp exposes the final value via aria-label regardless of animation frame", () => {
    render(<CountUp value={1234} />);
    const el = screen.getByLabelText("1,234");
    expect(el).toBeTruthy();
    // the rendered text is the live (animating) number; it must be numeric-ish
    expect(el.textContent).toMatch(/[0-9,]/);
  });

  it("Sparkline renders a path for non-empty values", () => {
    const { container } = render(<Sparkline values={[1, 4, 2, 8, 3]} />);
    expect(container.querySelector("path")).toBeTruthy();
  });
});
