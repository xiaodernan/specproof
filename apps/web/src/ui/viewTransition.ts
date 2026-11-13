/**
 * Route-change crossfade via the View Transitions API (Chromium), with an
 * honest fallback.
 *
 * <p>WHY: navigating between pages used to be a hard cut — the new page simply
 * replaced the old one. The View Transitions API lets the browser snapshot
 * both states and crossfade between them, which is the difference between
 * "a web app" and "a product". It must never change function:</p>
 *
 * <ul>
 *   <li>where the browser lacks the API (everything except Chromium 111+),
 *       the update runs exactly as before — no decoration either way;</li>
 *   <li>where the user prefers reduced motion, the update is NOT wrapped —
 *       motion that the user asked to be rid of is worse than a cut;</li>
 *   <li>where the API exists, the update is wrapped — the browser captures
 *       old and new snapshots and plays the default crossfade.</li>
 * </ul>
 */

export interface ViewTransitionCapableDocument {
  startViewTransition?: (update: () => void) => unknown;
}

function reducedMotionPreferred(): boolean {
  try {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return false; // no matchMedia → no preference signal → keep default behavior
    }
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches === true;
  } catch {
    return false;
  }
}

/** Run `update`, crossfading the view if the browser and the user's preferences allow. */
export function withViewTransition(update: () => void): void {
  if (reducedMotionPreferred()) {
    update();
    return;
  }
  const doc = document as unknown as ViewTransitionCapableDocument;
  if (typeof doc.startViewTransition === "function") {
    doc.startViewTransition(update);
    return;
  }
  update();
}
