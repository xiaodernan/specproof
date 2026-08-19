import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { Button } from "./Button";
import { XIcon } from "./icons";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
  closeOnBackdrop?: boolean;
}

const FOCUSABLE =
  "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])";

const EXIT_MS = 160;

export function Modal(props: ModalProps): JSX.Element | null {
  const { open, onClose, title, children, footer, size = "md", closeOnBackdrop = true } = props;

  const [renderIt, setRenderIt] = useState(open);
  const [visible, setVisible] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  const titleId = useId().replace(/[^a-zA-Z0-9_-]/g, "");

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  // Enter/exit choreography: mount, then flip the transition classes.
  useEffect(() => {
    if (open) {
      setRenderIt(true);
      const raf = requestAnimationFrame(() => setVisible(true));
      return () => cancelAnimationFrame(raf);
    }
    setVisible(false);
    const t = window.setTimeout(() => setRenderIt(false), EXIT_MS);
    return () => window.clearTimeout(t);
  }, [open]);

  // Focus management: move focus in, trap Tab, Escape closes, restore focus.
  // Depends on renderIt as well: the panel portal only exists once the
  // enter/exit choreography has committed it to the DOM.
  useEffect(() => {
    if (!open || !renderIt) return;
    restoreRef.current = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    const first = panel?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? panel ?? null)?.focus();

    const onKey = (e: KeyboardEvent): void => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab" || !panel) return;
      const nodes = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (nodes.length === 0) {
        e.preventDefault();
        panel.focus();
        return;
      }
      const firstEl = nodes[0];
      const lastEl = nodes[nodes.length - 1];
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === firstEl || !panel.contains(active)) {
          e.preventDefault();
          lastEl.focus();
        }
      } else if (active === lastEl || !panel.contains(active)) {
        e.preventDefault();
        firstEl.focus();
      }
    };

    document.addEventListener("keydown", onKey, true);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.body.style.overflow = prevOverflow;
      const target = restoreRef.current;
      if (target && document.contains(target)) target.focus();
    };
  }, [open, renderIt]);

  const onBackdropMouseDown = useCallback(
    (e: ReactMouseEvent<HTMLDivElement>): void => {
      if (closeOnBackdrop && e.target === e.currentTarget) onCloseRef.current();
    },
    [closeOnBackdrop]
  );

  if (!renderIt) return null;

  const rootCls = "ui-modal-root" + (visible ? " ui-modal-open" : " ui-modal-closed");

  return createPortal(
    <div className={rootCls}>
      <div className="ui-modal-backdrop" aria-hidden="true" onMouseDown={onBackdropMouseDown} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={"ui-modal-panel ui-modal-" + size}
      >
        <div className="ui-modal-head">
          <h2 className="ui-modal-title" id={titleId}>
            {title}
          </h2>
          <Button
            variant="ghost"
            size="sm"
            aria-label="关闭 Close"
            onClick={onCloseRef.current}
          >
            <XIcon size={14} />
          </Button>
        </div>
        <div className="ui-modal-body">{children}</div>
        {footer ? <div className="ui-modal-foot">{footer}</div> : null}
      </div>
    </div>,
    document.body
  );
}
