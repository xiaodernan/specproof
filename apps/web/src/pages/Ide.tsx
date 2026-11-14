import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { ANCHOR_DOCS, RUNBOOK } from "./ide.copy";
import "../styles/ide.css";

/**
 * SpecProof IDE （铁匠工坊）
 * A local-first, offline-friendly "IDE in a tab": a real anchor rail, a real
 * copy-board of commands that actually run in this repo, and a real notes
 * panel that writes to localStorage. No fake file system, no fake terminal —
 * the honesty of SpecProof is that every anchor points at a true file.
 *
 * Three panes: the rail to the docs, the copy-board of the day, the forge
 * notes. Nothing here emulates a cloud; the cloud *is* the same app, served.
 */

interface Note {
  id: string;
  title: string;
  body: string;
  updatedAt: number;
}

const NOTES_KEY = "specproof_ide_notes_v1";

function readNotes(): Note[] {
  try {
    const raw = globalThis.localStorage?.getItem(NOTES_KEY);
    return raw ? (JSON.parse(raw) as Note[]) : [];
  } catch {
    return [];
  }
}

function writeNotes(notes: Note[]): void {
  try {
    globalThis.localStorage?.setItem(NOTES_KEY, JSON.stringify(notes));
  } catch {
    /* quota full — the page stays alive, it just won't persist */
  }
}

export default function Ide() {
  const { t, locale } = useI18n();
  const [query, setQuery] = useState("");
  const [notes, setNotes] = useState<Note[]>(() => readNotes());
  const [activeId, setActiveId] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  const active = useMemo(() => notes.find((n) => n.id === activeId) ?? null, [notes, activeId]);
  const filteredRunbook = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return RUNBOOK;
    return RUNBOOK.filter((item) =>
      [item.id, item.title.zh, item.title.en, item.body, item.note.zh, item.note.en]
        .join(" ")
        .toLowerCase()
        .includes(q),
    );
  }, [query]);

  function addNote() {
    const now = Date.now();
    const note: Note = {
      id: `n-${now.toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
      title: t("ide.noteTitle"),
      body: "",
      updatedAt: now,
    };
    const next = [note, ...notes];
    setNotes(next);
    writeNotes(next);
    setActiveId(note.id);
    window.requestAnimationFrame(() => bodyRef.current?.focus());
  }

  function updateActive(patch: Partial<Pick<Note, "title" | "body">>) {
    if (!active) return;
    const next = notes.map((n) =>
      n.id === active.id ? { ...n, ...patch, updatedAt: Date.now() } : n,
    );
    setNotes(next);
    writeNotes(next);
  }

  function burnNote(id: string) {
    const next = notes.filter((n) => n.id !== id);
    setNotes(next);
    writeNotes(next);
    if (activeId === id) setActiveId(next[0]?.id ?? null);
  }

  function exportAll() {
    const stamp = new Date().toISOString().slice(0, 10);
    const text = notes
      .map((n) => `# ${n.title}\n\n${n.body}\n\n> ${new Date(n.updatedAt).toISOString()}`)
      .join("\n\n---\n\n");
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `specproof-notes-${stamp}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    setToast(t("ide.exportOk"));
    window.setTimeout(() => setToast(null), 1600);
  }

  const copy = useCallback(async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(id);
      window.setTimeout(() => setCopied(null), 1400);
    } catch {
      window.prompt("", text);
    }
  }, []);

  useEffect(() => {
    if (!activeId && notes.length > 0) setActiveId(notes[0].id);
  }, [activeId, notes]);

  return (
    <div className="ide-page">
      <div className="page-head">
        <h1>{t("ide.title")} <span className="ide-en">{t("ide.subtitle")}</span></h1>
        <div className="page-sub">{t("ide.lead")}</div>
      </div>

      {toast ? <div className="ide-toast" role="status">{toast}</div> : null}

      <div className="ide-shell">
        <nav className="ide-rail" aria-label={t("ide.railDocs")}>
          <p className="ide-kicker">{t("ide.railKicker")}</p>
          <ul>
            {ANCHOR_DOCS.map((doc) => (
              <li key={doc.label}>
                <a className="ide-anchor" href={doc.href} target="_blank" rel="noreferrer noopener">
                  <span className="ide-anchor-label">{doc.label}</span>
                  <span className="ide-anchor-note">{doc.detail[locale]}</span>
                </a>
              </li>
            ))}
          </ul>
          <p className="ide-foot">{t("ide.footNote")}</p>
        </nav>

        <section className="ide-runbook" aria-label={t("ide.runbookKicker")}>
          <div className="ide-section-head">
            <p className="ide-kicker">{t("ide.runbookKicker")}</p>
            <input
              className="ide-search"
              type="search"
              value={query}
              aria-label="filter"
              placeholder={locale === "zh" ? "过滤命令…" : "filter commands…"}
              onChange={(e) => setQuery(e.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          <ul className="ide-cmd-list">
            {filteredRunbook.map((cmd) => (
              <li key={cmd.id} className="ide-cmd">
                <div className="ide-cmd-top">
                  <strong>{cmd.title[locale]}</strong>
                </div>
                <div className="ide-cmd-body">
                  <code>{cmd.body}</code>
                  <button
                    type="button"
                    className="ide-copy"
                    aria-pressed={copied === cmd.id}
                    onClick={() => copy(cmd.id, cmd.body)}
                  >
                    {copied === cmd.id ? t("ide.copied") : t("ide.copy")}
                  </button>
                </div>
                <p className="ide-cmd-note">{cmd.note[locale]}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="ide-notes" aria-label={t("ide.notesKicker")}>
          <div className="ide-section-head ide-section-head-notes">
            <p className="ide-kicker">{t("ide.notesKicker")}</p>
            <div className="ide-note-actions">
              <button type="button" className="btn btn-ghost" onClick={addNote}>{t("ide.addNote")}</button>
              <button type="button" className="btn btn-ghost" onClick={exportAll}>{t("ide.exportAll")}</button>
            </div>
          </div>
          <div className="ide-notes-grid">
            <ul className="ide-note-list">
              {notes.length === 0 ? (
                <li className="ide-note-empty">{locale === "zh" ? "还没有便笺——按一下「新开一张」" : "No notes yet — press “New note”"}</li>
              ) : (
                notes.map((n) => (
                  <li key={n.id}>
                    <button
                      type="button"
                      className={"ide-note-item" + (activeId === n.id ? " is-active" : "")}
                      onClick={() => setActiveId(n.id)}
                    >
                      <span>{n.title || (locale === "zh" ? "（无题）" : "(untitled)")}</span>
                      <span className="ide-note-time">{new Date(n.updatedAt).toLocaleDateString(locale)}</span>
                    </button>
                    <button type="button" className="ide-burn" aria-label={t("ide.deleteNote")} onClick={() => burnNote(n.id)}>×</button>
                  </li>
                ))
              )}
            </ul>
            {active ? (
              <div className="ide-editor">
                <input
                  className="ide-note-title"
                  value={active.title}
                  aria-label={t("ide.noteTitle")}
                  onChange={(e) => updateActive({ title: e.target.value })}
                  placeholder={t("ide.noteTitle")}
                />
                <textarea
                  ref={bodyRef}
                  className="ide-note-body"
                  value={active.body}
                  onChange={(e) => updateActive({ body: e.target.value })}
                  placeholder={t("ide.notePlaceholder")}
                  spellCheck={false}
                />
              </div>
            ) : null}
          </div>
        </section>
      </div>
    </div>
  );
}
