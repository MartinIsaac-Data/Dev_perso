import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api, type Scope } from "../api/client";
import { Badge, Card, Empty, ErrorNote, Loading, LevelBar, Stat } from "../components/primitives";
import { useApi } from "../hooks/useApi";

// Eight domains at roughly 34px each. Tighter than this and the wrapped
// two-line category labels collide with their neighbours.
const DOMAIN_CHART_HEIGHT = 275;

export function Dashboard({
  scope,
  onOpenSkill,
}: {
  scope: Scope;
  onOpenSkill: (code: string) => void;
}) {
  const deps = [scope.profile, scope.asOf];
  const critical = useApi(() => api.criticalPath(scope, 8), deps);
  const decayed = useApi(() => api.decayed(scope), deps);
  const domains = useApi(() => api.domainSummary(scope), deps);
  const quotas = useApi(() => api.quotaStatus(scope, 6), deps);

  const error = critical.error ?? decayed.error ?? domains.error ?? quotas.error;
  if (error) {
    return <ErrorNote message={error} onRetry={critical.reload} />;
  }

  // `in_scope` excludes quarters that predate the trajectory: they carry no
  // quota, so they can neither be met nor missed.
  const closed = quotas.data?.filter((q) => !q.is_current && q.in_scope) ?? [];
  const silentQuarters = closed.filter((q) => q.is_silent);
  const missedQuarters = closed.filter((q) => !q.met);
  const totalGap = domains.data?.reduce((sum, d) => sum + d.total_gap, 0) ?? 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Levels to gain"
          value={totalGap}
          hint="Sum of every gap to target"
        />
        <Stat
          label="Decayed skills"
          value={decayed.data?.length ?? "—"}
          tone={(decayed.data?.length ?? 0) > 0 ? "bad" : "good"}
          hint="Past their practice window"
        />
        <Stat
          label="Quarters missed"
          value={missedQuarters.length}
          tone={missedQuarters.length > 0 ? "warn" : "good"}
          hint="Closed quarters below quota"
        />
        <Stat
          label="Silent quarters"
          value={silentQuarters.length}
          tone={silentQuarters.length > 0 ? "bad" : "good"}
          hint="Nothing published at all"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card
          title="What to work on next"
          subtitle="Ranked by how many wanted skills it unblocks, not by how central it looks"
        >
          {critical.loading ? (
            <Loading what="the critical path" />
          ) : !critical.data?.length ? (
            <Empty>Every targeted skill is at its target.</Empty>
          ) : (
            <ol className="space-y-2">
              {critical.data.map((skill, index) => (
                <li key={skill.code}>
                  <button
                    onClick={() => onOpenSkill(skill.code)}
                    className="flex w-full items-center gap-3 rounded px-2 py-1.5 text-left hover:bg-slate-50"
                  >
                    <span className="w-4 shrink-0 text-xs tabular-nums text-slate-400">
                      {index + 1}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium text-slate-800">
                          {skill.name}
                        </span>
                        {skill.is_blocked && (
                          <Badge tone="bad" title="A prerequisite is not yet at the required level">
                            blocked
                          </Badge>
                        )}
                      </span>
                      <span className="mt-1 flex items-center gap-2">
                        <LevelBar current={skill.current_level} target={skill.target_level} size="sm" />
                        <span className="text-xs text-slate-500">
                          gates {skill.blocks_below_target}
                        </span>
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </Card>

        <div className="space-y-4">
          <Card
            title="Losing ground"
            subtitle="Past the decay window. Includes skills already at target — those are the ones nobody checks."
          >
            {decayed.loading ? (
              <Loading what="decay" />
            ) : !decayed.data?.length ? (
              <Empty>Nothing has gone stale.</Empty>
            ) : (
              <ul className="space-y-1.5">
                {decayed.data.slice(0, 6).map((skill) => (
                  <li key={skill.code}>
                    <button
                      onClick={() => onOpenSkill(skill.code)}
                      className="flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left hover:bg-slate-50"
                    >
                      <span className="truncate text-sm text-slate-800">{skill.name}</span>
                      <Badge tone="bad">
                        {skill.months_since_practice}mo / {skill.decay_months}
                      </Badge>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Gap by domain" subtitle="Total levels still to gain">
            {domains.loading ? (
              <Loading what="domains" />
            ) : (
              <ResponsiveContainer width="100%" height={DOMAIN_CHART_HEIGHT}>
                <BarChart
                  data={domains.data ?? []}
                  layout="vertical"
                  margin={{ left: 4, right: 12, top: 4, bottom: 4 }}
                >
                  <CartesianGrid horizontal={false} stroke="#f1f5f9" />
                  <XAxis type="number" tick={{ fontSize: 11 }} stroke="#94a3b8" />
                  <YAxis
                    type="category"
                    dataKey="domain_name"
                    width={130}
                    // interval=0 forces every label to render. Recharts drops
                    // labels that do not fit by default, which silently hid
                    // half the domains and made the chart unreadable.
                    interval={0}
                    tick={{ fontSize: 10 }}
                    stroke="#94a3b8"
                  />
                  <Tooltip
                    cursor={{ fill: "#f8fafc" }}
                    contentStyle={{ fontSize: 12, borderRadius: 6 }}
                  />
                  <Bar dataKey="total_gap" name="levels to gain" radius={[0, 3, 3, 0]}>
                    {(domains.data ?? []).map((row) => (
                      <Cell
                        key={row.domain_code}
                        fill={row.decayed > 0 ? "#f43f5e" : "#0284c7"}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
