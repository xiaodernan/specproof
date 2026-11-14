import { useCallback, useEffect, useRef, useState } from "react";
import { Kbd } from "./Kbd";
import { XIcon } from "./icons";
import { SHORTCUT_GROUPS } from "./shortcuts";
import { useI18n } from "../i18n";

const isEditableTarget = (target: EventTarget | null): boolean => {
  if (!(target instanceof Element)) return false;
  if (target.closest('input, textarea, select, [contenteditable="true"]')) return true;
  return false;
};

/**
 * The keyboard shortcut card, toggled by "?" from anywhere outside an editable target.
 *
 * <p>Exists so the app's shortcuts are DISCOVERABLE without a manual — the palette
 * has an actions section and recent jobs, but nothing tells a first-day user
 * that "?" exists until they find it. Real products (Linear, GitHub, Vercel) all
 * ship this surface; so does SpecProof now.</p>
 *
 * <p>The shortcut list is data (ui/shortcuts.ts) and every row in it is wired to a
 * real handler. Opening is global but never hijacks the "?" typed into an input —
 * same editable-target guard the command palette uses.</p>
 */
export function ShortcutHelp(): JSX.Element | null {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const lastFocus = useRef<HTMLElement | null>(null);

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      if (event.defaultPrevented) return;
      if (isEditableTarget(event.target)) return;
      if (event.key === "?" && !event.ctrlKey && !event.metaKey && !event.altKey) {
        event.preventDefault();
        setOpen((prev) => !prev);
        return;
      }
      if (event.key === "Escape" && open) {
        event.stopPropagation();
        close();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);

  // Move focus into the dialog on open, and give it back on close — the
  // same focus contract the palette and modal already honor.
  useEffect(() => {
    if (open) {
      lastFocus.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null;
      panelRef.current?.focus();
    } else if (lastFocus.current) {
      lastFocus.current.focus();
      lastFocus.current = null;
    }
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="ui-shortcuts-root"
      role="dialog"
      aria-modal="true"
      aria-label={t("ui.shortcuts.ariaLabel")}
    >
      <div
        className="ui-shortcuts-backdrop"
        aria-hidden="true"
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) close();
        }}
      />
      <div className="ui-shortcuts-panel" ref={panelRef} tabIndex={-1}>
        <div className="ui-shortcuts-head">
          <div>
            <h2 className="ui-shortcuts-title">{t("ui.shortcuts.title")}</h2>
            <p className="ui-shortcuts-sub">{t("ui.shortcuts.sub")}</p>
          </div>
          <button type="button" className="ui-shortcuts-close" aria-label={t("ui.shortcuts.closeAria")} onClick={close}>
            <XIcon size={18} />
          </button>
        </div>
        <div className="ui-shortcuts-grid">
          {SHORTCUT_GROUPS.map((group) => (
            <section key={group.title.en} className="ui-shortcuts-group" aria-label={group.title[locale]}>
              <h3 className="ui-shortcuts-group-title">{group.title[locale]}</h3>
              <ul className="ui-shortcuts-list">
                {group.items.map((item) => (
                  <li key={item.label[locale]} className="ui-shortcuts-row">
                    <span className="ui-shortcuts-label">{item.label[locale]}</span>
                    <span className="ui-shortcuts-keys">
                      {item.keys.map((key, index) => (
                        <Kbd key={index}>{key}</Kbd>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
        <div className="ui-shortcuts-foot">
          <span className="ui-palette-hint"><Kbd>?</Kbd> {t("ui.shortcuts.close")}</span>
          <span className="ui-palette-hint"><Kbd>Esc</Kbd> {t("ui.shortcuts.close")}</span>
          <span className="ui-palette-hint"><Kbd>Ctrl</Kbd><Kbd>K</Kbd> {t("ui.shortcuts.palette")}</span>
        </div>
      </div>
    </div>
  );
}
