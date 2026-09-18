import type { ReactNode } from "react";

export type ProductIconName = "overview" | "verify" | "agent" | "matrix" | "contracts" | "team" | "chart" | "health" | "billing" | "guide" | "arrow" | "plus" | "shield" | "menu" | "close";

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
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
};

export function ProductIcon({ name, size = 20 }: { name: ProductIconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
