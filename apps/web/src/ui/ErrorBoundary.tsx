import { Component, type ReactNode } from "react";

// Render-crash fallback (guide §A row 32: 错误边界): when a route throws
// during render, the shell survives and shows this notice instead of a
// white screen. Errors are forwarded to the console for forensics.
// Class + testid are part of the W39 e2e/vitest contract.
export class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): { error: Error } {
    return { error };
  }

  componentDidCatch(error: Error): void {
    console.error("SpecProof render boundary caught:", error);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="errorbox" data-testid="error-boundary" role="alert">
          {"错误 ERROR — 页面渲染异常, 已降级 (error boundary): " +
            (this.state.error.message || String(this.state.error))}
          <div style={{ marginTop: 8 }}>
            <a className="btn btn-ghost btn-sm" href="#/dashboard">
              ← 返回总览
            </a>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
