import type { ReactNode } from "react";

export function Card({
  title,
  subtitle,
  right,
  children,
  className = "",
}: {
  title?: string;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-lg border border-slate-200 bg-white shadow-sm ${className}`}
    >
      {title && (
        <header className="flex items-start justify-between gap-4 border-b border-slate-100 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold tracking-tight text-slate-900">{title}</h2>
            {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
          </div>
          {right}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  tone = "neutral",
  hint,
}: {
  label: string;
  value: string | number;
  tone?: "neutral" | "warn" | "bad" | "good";
  hint?: string;
}) {
  const tones = {
    neutral: "text-slate-900",
    good: "text-emerald-700",
    warn: "text-amber-700",
    bad: "text-rose-700",
  } as const;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${tones[tone]}`}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

/**
 * Level as five segments rather than a number.
 *
 * Filled segments are the current level, outlined segments are the distance
 * to target. The gap is the thing worth seeing at a glance, and a bare "3/5"
 * does not show it.
 */
export function LevelBar({
  current,
  target,
  size = "md",
}: {
  current: number;
  target: number;
  size?: "sm" | "md";
}) {
  const height = size === "sm" ? "h-1.5" : "h-2";
  return (
    <div className="flex items-center gap-1" title={`level ${current} of a target of ${target}`}>
      {[1, 2, 3, 4, 5].map((step) => {
        const filled = step <= current;
        const wanted = step > current && step <= target;
        return (
          <span
            key={step}
            className={`${height} w-4 rounded-sm ${
              filled
                ? "bg-sky-600"
                : wanted
                  ? "border border-dashed border-sky-400 bg-sky-50"
                  : "bg-slate-200"
            }`}
          />
        );
      })}
    </div>
  );
}

export function Badge({
  children,
  tone = "neutral",
  title,
}: {
  children: ReactNode;
  tone?: "neutral" | "warn" | "bad" | "good" | "info";
  title?: string;
}) {
  const tones = {
    neutral: "bg-slate-100 text-slate-700 ring-slate-200",
    info: "bg-sky-50 text-sky-800 ring-sky-200",
    good: "bg-emerald-50 text-emerald-800 ring-emerald-200",
    warn: "bg-amber-50 text-amber-800 ring-amber-200",
    bad: "bg-rose-50 text-rose-800 ring-rose-200",
  } as const;
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Loading({ what }: { what: string }) {
  return <p className="py-8 text-center text-sm text-slate-400">Loading {what}…</p>;
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">
      <p>{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 rounded border border-rose-300 bg-white px-2 py-1 text-xs font-medium hover:bg-rose-100"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-slate-400">{children}</p>;
}
