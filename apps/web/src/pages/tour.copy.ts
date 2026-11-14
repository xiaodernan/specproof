import type { Locale } from "../i18n/strings";
import { TOUR_STATIONS, type TourStation } from "../ui/tour";

/**
 * The English edition of the tour's six stations.
 *
 * The station skeleton (id / route / numeral) is locale-independent and lives
 * in `ui/tour.ts`; only the prose differs. Keeping both editions side by side
 * here means the two languages can never drift apart in shape — a missing
 * English station would be a type error, not a silent blank.
 */

export const TOUR_STATIONS_EN: TourStation[] = [
  {
    id: "gate",
    numeral: "I",
    title: "The Gate · You push the door of SpecProof open",
    en: "THE GATE",
    chapter: "Station I · Arrival",
    narrate:
      "SpecProof does not care how many lines of code you wrote — it waits for you to open the door. The thing an acceptance officer respects most is evidence; no one enters without putting on the evidence goggles.",
    task: "Connect the workspace: sign in with your access token (sp_*) — it never leaves this browser.",
    tip: "No token? Ask an administrator for one. The token lives in this browser's sessionStorage and is never uploaded.",
    route: "#/",
    routeLabel: "Go to sign-in",
  },
  {
    id: "verdict",
    numeral: "II",
    title: "The Verdict · The first report you will read",
    en: "THE VERDICT",
    chapter: "Station II · Reading the file",
    narrate:
      "You stand before the first verification report. Verdict, matrix, evidence — every stat card asks the same question: did you actually read it?",
    task: "Open any #/jobs/{id} and read the four cards — verdict, contracts, failed, unverified — word by word.",
    tip: "Open the 'stages' tab and look at the stage timeline: not one timestamp there is invented.",
    route: "#/jobs",
    routeLabel: "Go to the verification list",
  },
  {
    id: "matrix",
    numeral: "III",
    title: "The Mountain · A matrix of iron",
    en: "THE MATRIX",
    chapter: "Station III · Reading the evidence",
    narrate:
      "The matrix is the summit of SpecProof. Every row is one requirement and one verdict; every cell says which kind of evidence it rests on — iron, or paper. Skip the matrix and you are only looking at a pretty screenshot.",
    task: "Open #/matrix, pick any row and ask: what is the evidence type? Is it base_pass_head_fail — iron — or static_analysis — 'possibly right'?",
    tip: "Open the findings detail behind a row and read the plain-language meaning of the evidence type.",
    route: "#/matrix",
    routeLabel: "Go to the matrix",
  },
  {
    id: "findings",
    numeral: "IV",
    title: "The Hall · What the discovery left behind",
    en: "THE DISCOVERY",
    chapter: "Station IV · Reading the traces",
    narrate:
      "Every finding is a fossil: it kept the trace of the problem, the place it touched, and how it turned its face between base and head.",
    task: "Open any #/jobs/{id} → risk findings tab, open one finding: is the severity a BLOCKER? Does the evidence_type read like iron, or like paper?",
    tip: "Hit 'Copy Markdown summary' and paste it anywhere — that is exactly how a reviewer reads it.",
    route: "#/jobs",
    routeLabel: "Go to the verification list",
  },
  {
    id: "epic",
    numeral: "V",
    title: "The Chronicler · The pen that becomes a scroll",
    en: "THE CHRONICLER",
    chapter: "Station V · Reading the scroll",
    narrate:
      "The chronicler writes only what truly happened. SpecProof pins every real process in the ledger, and any scroll you open can be matched against git log.",
    task: "Open #/epic and read any scroll: can you find the commit hash the chronicler's notes cite, in git log?",
    tip: "The chronicler loves small exact numbers — a 96.5% hit rate, a 2272-byte prefix — every digit lands in git.",
    route: "#/epic",
    routeLabel: "Go to the chronicles",
  },
  {
    id: "seal",
    numeral: "VI",
    title: "The Seal · Affix the mark of approval",
    en: "THE SEAL",
    chapter: "Station VI · Affixing the seal",
    narrate:
      "The tour ends here: you are no longer a visitor. The officer's trade is to doubt first and then trust — and you have just walked your first round of doubt. Put the mark on your name.",
    task: "Copy an Epic Certificate from any verification page, paste it to yourself, then come back and affix the final seal.",
    tip: "This mark is cut only into this browser's localStorage; another browser starts the walk over. Trust is earned a little at a time, like this.",
    route: "#/epic",
    routeLabel: "Go to the chronicles",
  },
];

export const TOUR_BY_LOCALE: Record<Locale, TourStation[]> = {
  zh: TOUR_STATIONS,
  en: TOUR_STATIONS_EN,
};
