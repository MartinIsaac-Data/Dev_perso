import { useState } from "react";

import { api, type Scope } from "../api/client";
import { Badge, Card, Empty, ErrorNote, LevelBar, Loading, Stat } from "../components/primitives";
import { useApi } from "../hooks/useApi";

/**
 * Gap Radar: what the market asks for, against what the profile holds.
 *
 * Two numbers are kept apart throughout, because collapsing them would hide
 * which problem you have. `demand_count` is how *common* a requirement is
 * across captured postings; `demanded_level` is how *deep* the deepest ask
 * goes. One posting wanting level 4 and nine wanting level 3 need different
 * responses.
 */
export function MarketView({ scope }: { scope: Scope }) {
  const [role, setRole] = useState<string>("");

  const gaps = useApi(
    () => api.marketGaps(scope, role || undefined),
    [scope.profile, role],
  );
  const roles = useApi(() => api.targetRoles(), []);
  const postings = useApi(() => api.postings(), []);
  const runs = useApi(() => api.agentRuns(), []);
  const reviews = useApi(() => api.periodicReviews(scope), [scope.profile]);

  if (gaps.error) return <ErrorNote message={gaps.error} onRetry={gaps.reload} />;
  if (gaps.loading || !gaps.data) return <Loading what="the market gap" />;

  const data = gaps.data;
  const short = data.demands.filter((d) => d.market_gap > 0);
  const critical = data.demands.filter((d) => d.is_critical);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setRole("")}
          className={`rounded-md px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${
            role === ""
              ? "bg-slate-900 text-white ring-slate-900"
              : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50"
          }`}
        >
          All roles
        </button>
        {(roles.data ?? []).map((entry) => (
          <button
            key={entry.code}
            onClick={() => setRole(entry.code)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${
              role === entry.code
                ? "bg-slate-900 text-white ring-slate-900"
                : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50"
            }`}
          >
            {entry.name}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Postings analysed" value={data.postings_analysed} />
        <Stat label="Skills demanded" value={data.demands.length} />
        <Stat
          label="Short of demand"
          value={short.length}
          tone={short.length > 0 ? "warn" : "good"}
        />
        <Stat
          label="Critical"
          value={critical.length}
          tone={critical.length > 0 ? "bad" : "good"}
          hint="Short, and a must-have in 2+ postings"
        />
      </div>

      {data.unmapped.length > 0 && (
        <div className="rounded-lg border border-sky-300 bg-sky-50 px-4 py-3">
          <p className="text-sm font-medium text-sky-900">
            {data.unmapped.length} requirement
            {data.unmapped.length > 1 ? "s" : ""} the taxonomy cannot express
          </p>
          <p className="mt-0.5 text-xs text-sky-800">
            {data.unmapped.map(([label, count]) => `${label} (${count})`).join(" · ")}
          </p>
          <p className="mt-1 text-[11px] text-sky-700">
            Not a failure of the extraction. The market is asking for something the
            taxonomy does not describe, which is the signal this module exists to find.
          </p>
        </div>
      )}

      <Card
        title="Where the market is ahead"
        subtitle="Gap is against the deepest level any captured posting asks for"
      >
        {!short.length ? (
          <Empty>Nothing demanded is beyond what this profile holds.</Empty>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
                <th className="py-1.5 pr-3 font-medium">Skill</th>
                <th className="py-1.5 pr-3 font-medium">Position</th>
                <th className="py-1.5 pr-3 text-right font-medium">Held</th>
                <th className="py-1.5 pr-3 text-right font-medium">Demanded</th>
                <th className="py-1.5 pr-3 text-right font-medium">Gap</th>
                <th className="py-1.5 text-right font-medium">Postings</th>
              </tr>
            </thead>
            <tbody>
              {short.map((demand) => (
                <tr key={demand.skill_code} className="border-b border-slate-50">
                  <td className="py-1.5 pr-3">
                    <span className="text-slate-800">{demand.skill_name}</span>
                    <span className="block font-mono text-[11px] text-slate-400">
                      {demand.skill_code}
                    </span>
                  </td>
                  <td className="py-1.5 pr-3">
                    <LevelBar
                      current={demand.current_level}
                      target={demand.demanded_level ?? demand.current_level}
                      size="sm"
                    />
                  </td>
                  <td className="py-1.5 pr-3 text-right tabular-nums text-slate-600">
                    {demand.current_level}
                  </td>
                  <td className="py-1.5 pr-3 text-right tabular-nums text-slate-900">
                    {demand.demanded_level ?? "—"}
                  </td>
                  <td className="py-1.5 pr-3 text-right">
                    <Badge tone={demand.is_critical ? "bad" : "warn"}>
                      +{demand.market_gap}
                    </Badge>
                  </td>
                  <td className="py-1.5 text-right text-xs tabular-nums text-slate-500">
                    {demand.must_have_count}/{demand.demand_count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card
        title="Captured postings"
        subtitle="Raw text retained in full, so a better prompt can re-process the corpus later"
      >
        {postings.loading ? (
          <Loading what="postings" />
        ) : (
          <div className="space-y-2">
            {(postings.data ?? []).map((posting) => (
              <div key={posting.id} className="rounded border border-slate-200 p-2.5">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-sm font-medium text-slate-900">{posting.title}</span>
                  <span className="text-[11px] text-slate-500">
                    {posting.company ?? "—"} · {posting.location ?? "—"} · captured{" "}
                    {posting.captured_on}
                  </span>
                </div>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {posting.requirements.map((requirement) => (
                    <Badge
                      key={requirement.raw_label}
                      tone={
                        requirement.skill_id === null
                          ? "info"
                          : requirement.importance === "must_have"
                            ? "neutral"
                            : "good"
                      }
                      title={
                        requirement.skill_id === null
                          ? "Not expressible in the taxonomy"
                          : requirement.evidence_quote ?? undefined
                      }
                    >
                      {requirement.raw_label}
                      {requirement.required_level ? ` @${requirement.required_level}` : ""}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {(reviews.data ?? []).length > 0 && (
        <Card title="Periodic reviews" subtitle="Generated, and kept so patterns are visible">
          <div className="space-y-3">
            {(reviews.data ?? []).map((review) => (
              <div key={review.id} className="rounded border border-slate-200 p-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-sm font-medium text-slate-900">
                    {review.kind} · {review.period_start} to {review.period_end}
                  </span>
                </div>
                <pre className="mt-2 whitespace-pre-wrap font-sans text-xs leading-relaxed text-slate-700">
                  {review.body_md}
                </pre>
                {review.next_action && (
                  <div className="mt-2 rounded bg-slate-50 px-2.5 py-2">
                    <p className="text-xs font-medium text-slate-900">
                      Next: {review.next_action}
                    </p>
                    {review.next_action_rationale && (
                      <p className="mt-0.5 text-[11px] text-slate-600">
                        {review.next_action_rationale}
                      </p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card
        title="Agent runs"
        subtitle="Every model call, with the hash of the prompt that produced it"
      >
        {runs.loading ? (
          <Loading what="agent runs" />
        ) : !(runs.data ?? []).length ? (
          <Empty>
            No agent has run yet. Set TOS_ANTHROPIC_API_KEY in .env, then use{" "}
            <code className="font-mono text-[11px]">tos agent review-case 1</code>.
          </Empty>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="py-1 pr-3 font-medium">Agent</th>
                <th className="py-1 pr-3 font-medium">Model</th>
                <th className="py-1 pr-3 font-medium">Status</th>
                <th className="py-1 pr-3 text-right font-medium">Tokens</th>
                <th className="py-1 font-medium">Prompt</th>
              </tr>
            </thead>
            <tbody>
              {(runs.data ?? []).map((run) => (
                <tr key={run.id} className="border-b border-slate-50">
                  <td className="py-1 pr-3 font-mono text-slate-700">{run.agent_name}</td>
                  <td className="py-1 pr-3 text-slate-500">{run.model}</td>
                  <td className="py-1 pr-3">
                    <Badge tone={run.status === "succeeded" ? "good" : "bad"}>
                      {run.status}
                    </Badge>
                  </td>
                  <td className="py-1 pr-3 text-right tabular-nums text-slate-500">
                    {run.input_tokens ?? 0}/{run.output_tokens ?? 0}
                  </td>
                  <td className="py-1">
                    {run.prompt_unchanged ? (
                      <span className="text-slate-500">unchanged</span>
                    ) : (
                      <Badge tone="warn" title="The prompt file has been edited since this run">
                        prompt changed since
                      </Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
