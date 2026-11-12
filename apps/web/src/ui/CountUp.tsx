import { useEffect, useRef, useState } from "react";

/**
 * CountUp — an animated number that eases from 0 to its target on mount (and
 * re-animates whenever the value changes, e.g. on a dashboard refresh).
 *
 * Accessibility: the final value is always exposed as `aria-label` so screen
 * readers and the contrast ruler see the real number, not the in-flight frames.
 * When the user prefers reduced motion the component jumps straight to the final
 * value with no animation. rAF is guarded so it also works under jsdom/tests.
 */
interface CountUpProps {
  value: number;
  durationMs?: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
  format?: (n: number) => string;
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

const raf: (cb: (t: number) => void) => number =
  typeof requestAnimationFrame === "function"
    ? (cb) => requestAnimationFrame(cb)
    : (cb) => setTimeout(() => cb(performance.now()), 16) as unknown as number;
const caf: (h: number) => void =
  typeof cancelAnimationFrame === "function" ? (h) => cancelAnimationFrame(h) : (h) => clearTimeout(h);

export function CountUp({
  value,
  durationMs = 900,
  decimals = 0,
  prefix = "",
  suffix = "",
  className,
  format,
}: CountUpProps): JSX.Element {
  const [display, setDisplay] = useState<number>(() => (prefersReducedMotion() ? value : 0));
  const handle = useRef<number | null>(null);

  useEffect(() => {
    if (prefersReducedMotion()) {
      setDisplay(value);
      return;
    }
    const start = performance.now();
    const from = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(from + (value - from) * eased);
      if (t < 1) {
        handle.current = raf(tick);
      } else {
        setDisplay(value);
      }
    };
    handle.current = raf(tick);
    return () => {
      if (handle.current !== null) caf(handle.current);
    };
  }, [value, durationMs]);

  const finalText = format
    ? format(value)
    : prefix + value.toLocaleString("en-US", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }) + suffix;
  const liveText = format
    ? format(display)
    : prefix + display.toLocaleString("en-US", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }) + suffix;

  return (
    <span className={className} aria-label={finalText}>
      {liveText}
    </span>
  );
}
