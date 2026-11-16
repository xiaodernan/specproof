import { storedLocale } from "../i18n/strings";

export function Spinner(): JSX.Element {
  return <div className="spinner">{storedLocale() === "zh" ? "加载中" : "Loading…"}</div>;
}
