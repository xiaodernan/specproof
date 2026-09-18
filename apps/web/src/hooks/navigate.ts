// Hash-router navigation helpers. The app routes on window.location.hash
// (see App.tsx), so navigation is just a hash assignment; this hook keeps
// pages free of stringly-typed "#/..." concat and normalises leading slash.

export function navigateTo(path: string): void {
  const normalised = path.startsWith("/") ? path : "/" + path;
  window.location.hash = "#" + normalised;
}

export function useNavigate(): (path: string) => void {
  return navigateTo;
}
