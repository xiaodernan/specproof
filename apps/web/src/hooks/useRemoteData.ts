import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../api";

/** One active request per view, cancelled on navigation; polling pauses in hidden tabs. */
export function useRemoteData<T>(path: string | null, pollInterval = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(!!path);
  const [refreshing, setRefreshing] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision(value => value + 1), []);

  useEffect(() => {
    let alive = true;
    let inFlight = false;
    let controller: AbortController | null = null;
    let timeout: number | undefined;
    setData(null);
    setError(null);
    setUpdatedAt(null);
    setLoading(!!path);
    if (!path) { setRefreshing(false); return; }
    const load = async () => {
      if (inFlight || !alive) return;
      inFlight = true;
      controller = new AbortController();
      let timedOut = false;
      timeout = window.setTimeout(() => { timedOut = true; controller?.abort(); }, 20000);
      setRefreshing(true);
      try {
        const response = await apiGet<T>(path, controller.signal);
        if (!alive) return;
        setData(response);
        setError(null);
        setUpdatedAt(new Date().toISOString());
      } catch (cause) {
        if (!alive) return;
        setData(null);
        setError(timedOut ? new Error("服务响应超时，请稍后重试。") : cause instanceof Error ? cause : new Error(String(cause)));
      } finally {
        window.clearTimeout(timeout);
        inFlight = false;
        if (alive) { setLoading(false); setRefreshing(false); }
      }
    };
    void load();
    const onVisible = () => { if (document.visibilityState === "visible") void load(); };
    const timer = pollInterval > 0 ? window.setInterval(onVisible, pollInterval) : undefined;
    if (pollInterval > 0) document.addEventListener("visibilitychange", onVisible);
    return () => {
      alive = false;
      controller?.abort();
      window.clearTimeout(timeout);
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [path, pollInterval, revision]);

  return { data, error, loading, refreshing, updatedAt, refresh };
}

export function useDebouncedValue(value: string, delay = 300) {
  const [settled, setSettled] = useState(value.trim());
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value.trim()), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return settled;
}
