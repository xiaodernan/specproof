# SpecProof Design System — Phase 1 Foundation

The visual-overhaul foundation ("Aurora") for the SpecProof SPA. Dark-first with a full
light theme, hairline borders, layered elevation, tight typography, restrained motion and
keyboard-first interactions. Page adoption happens in phase 2; this phase ships the system
plus a living style guide at `#/ui-kit` (standalone — reviewable without an API key).

## Design decisions

- **Accent — "Aurora"**: electric violet `#7C5CFF` (`--accent-500`) paired with cyan
  `#22D3EE` (`--accent-2-400`); `--gradient-aurora` powers hero text, the primary button
  and the brand mark. Neutrals are a zinc ramp (`--zinc-0`…`--zinc-950`).
- **Theming**: CSS custom properties under `:root` (dark default) and
  `:root[data-theme="light"]`; `data-theme` lives on `<html>`. An inline bootstrap in
  `index.html` resolves `localStorage["specproof_theme"]` (light | dark | system) before
  first paint, so there is no flash. `ThemeProvider` hydrates the same key, follows OS
  `prefers-color-scheme` changes while the preference is "system", and exposes
  `useTheme()` (theme / resolved / setTheme / toggle).
- **Typography**: Inter-first system stack, 11–30px scale, tight heading tracking,
  `tabular-nums` for every metric (via `.ui-kit-num`), mono stack for IDs/timestamps.
- **Structure**: 4px spacing grid (`--sp-1`…`--sp-16`), radii 6/8/12/16, control heights
  24/28/32/36/40, four elevation levels (`--elev-1`…`--elev-4`), blur 4/8/16, motion
  120/160/240ms on a standard ease-out. All animation collapses under
  `prefers-reduced-motion: reduce`.
- **Status semantics**: success / warning / danger / info each carry fg, tint and on-solid
  variants tuned for WCAG AA in both themes.

## File map

| Area | Files |
| --- | --- |
| Tokens | `src/theme/tokens.css` |
| Theme system | `src/theme/ThemeProvider.tsx`, `src/theme/useTheme.ts` |
| Global base | `src/styles/base.css` (imported after the legacy `styles.css`, which is untouched) |
| Components | `src/ui/*` (21 components + icons + barrel + recent-jobs store) |
| Style guide | `src/ui-kit/UiKit.tsx` (route `#/ui-kit`), `src/ui-kit/ControlRoomPreview.tsx` |
| Shell wiring | `src/App.tsx` (ThemeProvider + ToastProvider + CommandPalette + ui-kit route), `src/main.tsx`, `index.html` |

## Component inventory (21)

Button (primary/secondary/ghost/danger × sm/md/lg, loading), Card, Badge (6 tones),
StatusDot (running pulse), Table (sortable, dense, sticky header, empty state), Tabs
(roving tabindex, arrow keys), Modal (portal, focus trap, ESC, focus restore, 160ms
exit), Tooltip (hover/focus, 300ms delay, 4 sides), Toast/Toaster (stacked viewport,
auto-dismiss, hover pause), Skeleton (shimmer ×3 variants), EmptyState, Input, Select,
Textarea, Checkbox (indeterminate), Progress, Timeline, Breadcrumbs, Kbd,
CommandPalette (Ctrl/Cmd+K: all `/agent/*` + console routes, theme toggle, recent jobs
from `localStorage["specproof_recent_jobs"]`), FieldShell (label + error + hint).

## Gates

`npm run typecheck` (tsc strict) · `npm run test` (vitest, jsdom) · `npm run build`.
New tests: ThemeProvider (4), Button (4), Table (4), Modal (4), CommandPalette (4),
UiKit smoke (2) — 22 new cases on top of the existing 33.

## Phase 2 (page adoption) — what it will touch

Existing page files remain untouched until phase 2. Adoption will swap page-local markup
for `src/ui` components and `base.css` classes in: `src/pages/*` (Dashboard, Jobs,
JobDetail, Matrix, FindingDetail, Contracts, Eval, Health, Login), `src/agent/pages/*`,
`src/identity/pages/*`, plus the shell chrome in `src/App.tsx` (sidebar/brand/nav) and
the legacy `src/styles.css`/ `src/components.tsx` (retired as pages migrate). Job pages
will call `recordRecentJob()` so the palette's recent-jobs section fills up organically.
