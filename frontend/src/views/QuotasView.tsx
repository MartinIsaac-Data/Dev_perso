import { api, type Scope } from "../api/client";
import type { QuarterStatus } from "../api/types";
import { Badge, Card, Empty, ErrorNote, Loading } from "../components/primitives";
import { useApi } from "../hooks/useApi";

/**
 * Quarter by quarter, never as a running annual total.
 *
 * An annual target is satisfiable by a burst in December, and an annual
 * progress bar would call that a success right up until it was too late to
 * do anything about it. The whole point of this view is that a silent quarter
 * is impossible to miss.
 */
export function QuotasView({ scope }: { scope: Scope }) {
  const quotas = useApi(() => api.quotaStatus(scope, 8), [scope.profile, scope.asOf]);
  const phases = useApi(() => api.phases(), []);

  if (quotas.error) return <ErrorNote message={quotas.error} onRetry={quotas.reload} />;
  if (quotas.loading) return <Loading what="quotas" />;
  if (!quotas.data?.length) return <Empty>No quarters to report.</Empty>;

  // Only quarters the trajectory actually made a demand of can be silent.
  // Counting the history that predates the plan as a run of failures would
  // be the kind of dishonest metric this whole system exists to avoid.
  const closed = quotas.data.filter((q) => !q.is_current && q.in_scope);
  const silent = closed.filter((q) => q.is_silent);

  return (
    <div className="space-y-4">
      {silent.length > 0 && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3">
          <p className="text-sm font-medium text-rose-900">
            {silent.length} closed quarter{silent.length > 1 ? "s" : ""} with nothing published at
            all: {silent.map((q) => `${q.year} Q${q.quarter}`).join(", ")}.
          </p>
          <p className="mt-0.5 text-xs text-rose-800">
            Not a shortfall against a type — no deliverable of any kind was shipped.
          </p>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {quotas.data.map((quarter) => (
          <QuarterCard key={`${quarter.year}Q${quarter.quarter}`} quarter={quarter} />
        ))}
      </div>

      <Card title="The trajectory" subtitle="Quotas are a property of the phase, and are per quarter">
        {phases.loading ? (
          <Loading what="phases" />
        ) : (
          <div className="space-y-3">
            {(phases.data ?? []).map((phase) => (
              <div
                key={phase.code}
                className={`rounded-md border p-3 ${
                  phase.is_current ? "border-sky-300 bg-sky-50" : "border-slate-200"
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold text-slate-900">{phase.name}</h3>
                  <span className="text-xs text-slate-500">
                    {phase.starts_on.slice(0, 4)}–{phase.ends_on.slice(0, 4)}
                  </span>
                  {phase.is_current && <Badge tone="info">current</Badge>}
                </div>
                {phase.objective && (
                  <p className="mt-1 text-xs leading-relaxed text-slate-600">{phase.objective}</p>
                )}
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {phase.quotas
                    .filter((quota) => quota.min_per_quarter > 0)
                    .map((quota) => (
                      <Badge key={quota.type_code}>
                        {quota.min_per_quarter}× {quota.type_name} / quarter
                      </Badge>
                    ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function QuarterCard({ quarter }: { quarter: QuarterStatus }) {
  const tone = !quarter.in_scope
    ? "border-slate-200 bg-slate-50"
    : quarter.is_current
      ? "border-slate-300"
      : quarter.is_silent
        ? "border-rose-300 bg-rose-50"
        : quarter.met
          ? "border-emerald-200"
          : "border-amber-300 bg-amber-50";

  return (
    <div className={`rounded-lg border bg-white p-3 ${tone}`}>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">
          {quarter.year} Q{quarter.quarter}
        </h3>
        {!quarter.in_scope ? (
          <Badge>no target</Badge>
        ) : quarter.is_current ? (
          <Badge tone="info">in progress</Badge>
        ) : quarter.is_silent ? (
          <Badge tone="bad">silent</Badge>
        ) : quarter.met ? (
          <Badge tone="good">met</Badge>
        ) : (
          <Badge tone="warn">missed</Badge>
        )}
      </div>

      <p className="mt-0.5 text-[11px] text-slate-500">
        {quarter.phase_name ?? "before the trajectory"} · {quarter.total_published} published
      </p>

      {quarter.lines.length === 0 ? (
        <p className="mt-2 text-xs text-slate-400">
          Outside the trajectory — nothing was required of this quarter.
        </p>
      ) : (
        <ul className="mt-2 space-y-1.5">
          {quarter.lines.map((line) => (
            <li key={line.type_code} className="flex items-center gap-2">
              <span className="flex-1 truncate text-xs text-slate-600">{line.type_name}</span>
              <span className="flex gap-0.5">
                {Array.from({ length: Math.max(line.required, line.published) }).map((_, index) => (
                  <span
                    key={index}
                    className={`h-2.5 w-2.5 rounded-sm ${
                      index < line.published
                        ? "bg-sky-600"
                        : "border border-dashed border-slate-300"
                    }`}
                  />
                ))}
              </span>
              <span
                className={`w-8 text-right text-xs tabular-nums ${
                  line.met ? "text-slate-500" : "font-medium text-amber-700"
                }`}
              >
                {line.published}/{line.required}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
