import { useState } from "react";

import { api, type Scope } from "../api/client";
import { Badge, Card, Empty, ErrorNote, Loading } from "../components/primitives";
import { useApi } from "../hooks/useApi";

/**
 * The CV, and the part of it that would not survive an interview.
 *
 * Every claim is listed with the artefacts behind it. A level of 3 or above
 * with nothing published is flagged — not as an accusation, but because that
 * is the line somebody else will find first, and it is better found here.
 */
export function EvidenceView({ scope }: { scope: Scope }) {
  const [minLevel, setMinLevel] = useState(3);
  const evidence = useApi(() => api.evidenceCv(scope, minLevel), [scope.profile, minLevel]);

  if (evidence.error) return <ErrorNote message={evidence.error} onRetry={evidence.reload} />;

  const rows = evidence.data ?? [];
  const weak = rows.filter((row) => !row.is_defensible);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-xs text-slate-600">
          Claims from level
          <select
            value={minLevel}
            onChange={(event) => setMinLevel(Number(event.target.value))}
            className="ml-2 rounded border border-slate-200 px-2 py-1 text-xs"
          >
            {[2, 3, 4, 5].map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </label>
        <span className="text-xs text-slate-500">
          {rows.length} claims · {weak.length} without a published artefact
        </span>
      </div>

      {weak.length > 0 && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3">
          <p className="text-sm font-medium text-amber-900">
            {weak.length} skill{weak.length > 1 ? "s" : ""} claimed at level {minLevel} or above with
            nothing published behind {weak.length > 1 ? "them" : "it"}.
          </p>
          <p className="mt-0.5 text-xs text-amber-800">
            {weak.map((row) => row.skill_name).join(", ")}.
          </p>
        </div>
      )}

      {evidence.loading ? (
        <Loading what="the evidence base" />
      ) : !rows.length ? (
        <Empty>No claims at that level yet.</Empty>
      ) : (
        <div className="space-y-2">
          {rows.map((row) => (
            <article
              key={row.skill_code}
              className={`rounded-lg border bg-white p-3 ${
                row.is_defensible ? "border-slate-200" : "border-amber-300"
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="text-sm font-medium text-slate-900">
                    {row.skill_name}
                    <span className="ml-2 font-normal text-slate-400">level {row.current_level}</span>
                  </h3>
                  <p className="text-[11px] text-slate-500">{row.domain_name}</p>
                </div>
                {!row.is_defensible && <Badge tone="warn">no published artefact</Badge>}
              </div>

              {row.evidence.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {row.evidence.map((item) => (
                    <li key={item.deliverable_id} className="flex flex-wrap items-center gap-2">
                      <span className="text-xs text-slate-700">{item.title}</span>
                      <span className="text-[11px] text-slate-400">
                        {item.type_name}
                        {item.published_on ? ` · ${item.published_on}` : " · unpublished"}
                      </span>
                      {item.cited_for_promotion && (
                        <Badge tone="info" title="Cited to justify a level change">
                          cited as evidence
                        </Badge>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </div>
      )}

      <Card title="How to read this">
        <p className="text-xs leading-relaxed text-slate-600">
          A skill marked <em>cited as evidence</em> was named when the level was raised, and the
          database refuses a promotion without one. A skill with artefacts but no citation was
          exercised without a formal level change — still evidence, just weaker. A skill with
          nothing at all is a claim resting on memory.
        </p>
      </Card>
    </div>
  );
}
