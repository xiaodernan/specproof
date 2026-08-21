import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { Button } from "../Button";
import { Modal } from "../Modal";

function Host(): JSX.Element {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>打开</button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="确认操作"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button variant="primary" onClick={() => setOpen(false)}>
              确认
            </Button>
          </>
        }
      >
        <p>对话框内容</p>
      </Modal>
    </>
  );
}

describe("Modal", () => {
  it("does not render while closed", () => {
    render(<Host />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens, traps focus inside and closes on Escape, restoring focus", async () => {
    render(<Host />);
    const trigger = screen.getByRole("button", { name: "打开" });
    trigger.focus();
    fireEvent.click(trigger);

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeTruthy();
    expect(screen.getByText("确认操作")).toBeTruthy();

    // Focus moved inside the dialog (close button is the first focusable).
    expect(dialog.contains(document.activeElement)).toBe(true);

    // Tab on the last focusable wraps back to the first focusable.
    const buttons = Array.from(
      dialog.querySelectorAll<HTMLElement>("button:not([disabled])")
    );
    const last = buttons[buttons.length - 1];
    last.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(buttons[0]);

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(trigger);
  });

  it("calls onClose when the backdrop is clicked", async () => {
    render(<Host />);
    fireEvent.click(screen.getByRole("button", { name: "打开" }));
    const backdrop = document.querySelector(".ui-modal-backdrop");
    expect(backdrop).toBeTruthy();
    fireEvent.mouseDown(backdrop as Element);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("ignores Escape while closed", () => {
    const onClose = vi.fn();
    render(
      <Modal open={false} onClose={onClose} title="未打开" />
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });
});
