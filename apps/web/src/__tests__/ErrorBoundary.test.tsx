import { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "../components";

function Boom(): ReactNode {
  throw new Error("kaboom-fixture");
}

describe("ErrorBoundary", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders children untouched when nothing throws", () => {
    render(
      <ErrorBoundary>
        <div>healthy child</div>
      </ErrorBoundary>
    );
    expect(screen.getByText("healthy child")).toBeTruthy();
    expect(screen.queryByTestId("error-boundary")).toBeNull();
  });

  it("renders the degradation notice when a child crashes", () => {
    // React logs render errors to console.error; keep the test output clean.
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    );
    expect(screen.getByTestId("error-boundary")).toBeTruthy();
    expect(screen.getByText(/kaboom-fixture/)).toBeTruthy();
    expect(screen.getByText(/错误 ERROR/)).toBeTruthy();
  });
});
