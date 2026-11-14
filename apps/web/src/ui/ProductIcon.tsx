import type { ReactNode } from "react";

export type ProductIconName = "overview" | "verify" | "agent" | "matrix" | "contracts" | "team" | "chart" | "health" | "billing" | "guide" | "arrow" | "plus" | "shield" | "menu" | "close" | "scroll" | "invert" | "hammer" | "map" | "book" | "lantern" | "gazette" | "calendar";

const paths: Record<ProductIconName, ReactNode> = {
  overview: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  verify: <><path d="M9 4H5a2 2 0 0 0-2 2v14h16V6a2 2 0 0 0-2-2h-4" /><rect x="8" y="2" width="6" height="4" rx="1" /><path d="m7 12 3 3 5-5" /></>,
  agent: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z" /><path d="m20 2 .5 1.5L22 4l-1.5.5L20 6l-.5-1.5L18 4l1.5-.5Z" /></>,
  matrix: <><rect x="3" y="3" width="18" height="18" rx="3" /><path d="M3 9h18M9 9v12M15 9v12M3 15h18" /></>,
  contracts: <><path d="M14 2H5v20h14V7Z" /><path d="M14 2v6h5M8 12h8M8 16h6" /></>,
  team: <><circle cx="9" cy="8" r="3" /><path d="M3 21v-3a6 6 0 0 1 12 0v3M17 5a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v3" /></>,
  chart: <><path d="M4 3v17h17M8 15v-4M13 15V7M18 15V4" /></>,
  health: <><path d="M2 12h5l3-8 4 16 3-8h5" /></>,
  billing: <><rect x="2" y="5" width="20" height="14" rx="3" /><path d="M2 10h20M6 15h4" /></>,
  guide: <><path d="M12 5C9 2 4 3 2 4v16c3-2 7-2 10 0 3-2 7-2 10 0V4c-2-1-7-2-10 1Zm0 0v15" /></>,
  arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  shield: <><path d="m12 2 9 4v6c0 5-6 9-9 10-3-1-9-5-9-10V6Z" /><path d="m8 12 3 3 5-6" /></>,
  scroll: <><path d="M8 3H4v18h14V7Z" /><path d="M8 3v6h10M8 12h8M8 16h6M14 3h6" /><path d="M19.5 3.5 17 6" /></>,
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  invert: <><path d="M12 3v18" /><path d="m8 7 4-4 4 4" /><path d="m8 17 4 4 4-4" /></>,
  hammer: <><path d="M15 4 10 9l5 5 5-5Z" /><path d="M9 15l-6 6" /></>,
  map: <><path d="M9 4 3 6v16l6-2M9 4l6 2M9 4v16M15 6l6-2v16l-6 2M15 6v16M15 6l-6-2" /></>,
  book: <><path d="M4 5a2 2 0 0 1 2-2h14v16H6a2 2 0 0 0-2 2Z" /><path d="M4 19a2 2 0 0 1 2-2h14" /><path d="M9 7h6M9 11h4" /></>,
  lantern: <><path d="M9 3h6M10 3v2h4V3M8 9a4 4 0 0 1 8 0v5a4 4 0 0 1-8 0Z" /><path d="M12 10.5c.9 1.1 1.2 1.8 0 3.1-1.2-1.3-.9-2 0-3.1Z" /><path d="M10.5 17.5h3M12 17.5V21" /></>,
  gazette: <><path d="M3 5h13a2 2 0 0 1 2 2v12H5a2 2 0 0 1-2-2V5Z" /><path d="M18 9h3v8a2 2 0 0 1-2 2" /><path d="M6 9h7M6 13h7M6 17h4" /></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M8 3v4M16 3v4M3 10.5h18" /><path d="M7.5 15h2M11.5 15h2M15.5 15h2M7.5 18h2M11.5 18h2" /></>,
};

export function ProductIcon({ name, size = 20 }: { name: ProductIconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
