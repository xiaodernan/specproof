import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Button } from "./Button";
import { XIcon } from "./icons";

export type ToastTone = "info" | "success" | "warning" | "danger";

export interface ToastOptions {
  title: string;
  description?: string;
  tone?: ToastTone;
  /** Auto-dismiss delay in ms; 0 keeps the toast until dismissed. */
  duration?: number;
}

export interface ToastItem {
  id: number;
  title: string;
  description?: string;
  tone: ToastTone;
  duration: number;
}

export interface ToastContextValue {
  toasts: ToastItem[];
  toast: (options: ToastOptions) => number;
  dismiss: (id: number) => void;
  dismissAll: () => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const DEFAULT_DURATION = 4500;
const EXIT_MS = 140;

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used inside <ToastProvider>");
  }
  return ctx;
}

export function ToastProvider(props: { children?: ReactNode }): JSX.Element {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const idRef = useRef(0);
  const timers = useRef(new Map<number, number>());

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer !== undefined) {
      window.clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const dismissAll = useCallback(() => {
    timers.current.forEach((timer) => window.clearTimeout(timer));
    timers.current.clear();
    setToasts([]);
  }, []);

  const toast = useCallback(
    (options: ToastOptions): number => {
      const id = ++idRef.current;
      const item: ToastItem = {
        id,
        title: options.title,
        description: options.description,
        tone: options.tone ?? "info",
        duration: options.duration ?? DEFAULT_DURATION,
      };
      setToasts((prev) => [...prev.slice(-4), item]);
      return id;
    },
    []
  );

  const value = useMemo(
    () => ({ toasts, toast, dismiss, dismissAll }),
    [toasts, toast, dismiss, dismissAll]
  );

  return (
    <ToastContext.Provider value={value}>
      {props.children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

function ToastViewport(props: { toasts: ToastItem[]; onDismiss: (id: number) => void }): JSX.Element {
  return (
    <div className="ui-toast-viewport" role="status" aria-live="polite" aria-label="通知 Notifications">
      {props.toasts.map((item) => (
        <ToastCard key={item.id} item={item} onDismiss={props.onDismiss} />
      ))}
    </div>
  );
}

function ToastCard(props: { item: ToastItem; onDismiss: (id: number) => void }): JSX.Element {
  const { item, onDismiss } = props;
  const [exiting, setExiting] = useState(false);
  const [paused, setPaused] = useState(false);

  const beginExit = useCallback(() => {
    setExiting(true);
    window.setTimeout(() => onDismiss(item.id), EXIT_MS);
  }, [item.id, onDismiss]);

  useEffect(() => {
    if (item.duration <= 0 || paused) return;
    const timer = window.setTimeout(beginExit, item.duration);
    return () => window.clearTimeout(timer);
  }, [item.duration, paused, beginExit]);

  return (
    <div
      className={"ui-toast ui-toast-" + item.tone + (exiting ? " ui-toast-exit" : "")}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <span className="ui-toast-bar" aria-hidden="true" />
      <div className="ui-toast-body">
        <div className="ui-toast-title">{item.title}</div>
        {item.description ? <div className="ui-toast-desc">{item.description}</div> : null}
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="ui-toast-close"
        aria-label="关闭通知 Dismiss"
        onClick={beginExit}
      >
        <XIcon size={12} />
      </Button>
    </div>
  );
}
