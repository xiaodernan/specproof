import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export interface TabItem {
  id: string;
  label: ReactNode;
  disabled?: boolean;
  content?: ReactNode;
}

export interface TabsProps {
  items: TabItem[];
  value?: string;
  defaultValue?: string;
  onChange?: (id: string) => void;
  ariaLabel?: string;
  className?: string;
}

export function Tabs(props: TabsProps): JSX.Element {
  const { items, value, defaultValue, onChange, ariaLabel, className } = props;
  const [inner, setInner] = useState<string>(defaultValue ?? items[0]?.id ?? "");
  const activeId = value !== undefined ? value : inner;
  const listRef = useRef<HTMLDivElement>(null);

  const select = (id: string): void => {
    if (value === undefined) setInner(id);
    if (onChange) onChange(id);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>): void => {
    const enabled = items.filter((it) => !it.disabled).map((it) => it.id);
    if (enabled.length === 0) return;
    const idx = enabled.indexOf(activeId);
    let next: number | null = null;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      next = idx < 0 ? 0 : (idx + 1) % enabled.length;
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      next = idx <= 0 ? enabled.length - 1 : idx - 1;
    } else if (e.key === "Home") {
      next = 0;
    } else if (e.key === "End") {
      next = enabled.length - 1;
    }
    if (next !== null) {
      e.preventDefault();
      const id = enabled[next];
      select(id);
      const esc = id.replace(/"/g, '\\"');
      listRef.current
        ?.querySelector<HTMLButtonElement>('[data-tab="' + esc + '"]')
        ?.focus();
    }
  };

  const activeItem = items.find((it) => it.id === activeId);

  return (
    <div className={"ui-tabs" + (className ? " " + className : "")}>
      <div
        role="tablist"
        aria-label={ariaLabel ?? "Tabs"}
        className="ui-tablist"
        onKeyDown={onKeyDown}
        ref={listRef}
      >
        {items.map((it) => (
          <button
            key={it.id}
            type="button"
            role="tab"
            data-tab={it.id}
            id={"ui-tab-" + it.id}
            aria-selected={it.id === activeId}
            aria-controls={"ui-tabpanel-" + it.id}
            tabIndex={it.id === activeId ? 0 : -1}
            className="ui-tab"
            disabled={it.disabled}
            onClick={() => select(it.id)}
          >
            {it.label}
          </button>
        ))}
      </div>
      {activeItem && activeItem.content !== undefined ? (
        <div
          role="tabpanel"
          id={"ui-tabpanel-" + activeItem.id}
          aria-labelledby={"ui-tab-" + activeItem.id}
          className="ui-tabpanel"
          key={activeId}
        >
          {activeItem.content}
        </div>
      ) : null}
    </div>
  );
}
