import { useMemo, useState } from "react";

import { api, type Scope } from "../api/client";
import type { SkillPosition } from "../api/types";
import { SkillNeighbourhood } from "../components/SkillNeighbourhood";
import { Badge, Card, Empty, ErrorNote, LevelBar, Loading } from "../components/primitives";
import { useApi } from "../hooks/useApi";

type Filter = "all" | "wanted" | "available" | "blocked" | "decayed";

const FILTERS: { key: Filter; label: string; hint: string }[] = [
  { key: "wanted", label: "Below target", hint: "Everything with a gap" },
  { key: "available", label: "Startable", hint: "Below target, prerequisites satisfied" },
  { key: "blocked", label: "Blocked", hint: "Below target, gated by a prerequisite" },
  { key: "decayed", label: "Decayed", hint: "Past the practice window" },
  { key: "all", label: "All", hint: "The whole taxonomy" },
];

export function SkillsView({
  scope,
  selectedCode,
  onSelect,
}: {
  scope: Scope;
  selectedCode: string | null;
  onSelect: (code: string | null) => void;
}) {
  const [filter, setFilter] = useState<Filter>("wanted");
  const [search, setSearch] = useState("");

  const positions = useApi(() => api.positions(scope), [scope.profile, scope.asOf]);
  const graph = useApi(() => api.graph(), []);

  const byCode = useMemo(
    () => new Map((positions.data ?? []).map((p) => [p.code, p])),
    [positions.data],
  );

  const visible = useMemo(() => {
    let rows = positions.data ?? [];
    if (filter === "wanted") rows = rows.filter((p) => p.gap > 0);
    if (filter === "available") rows = rows.filter((p) => p.is_available);
    if (filter === "blocked") rows = rows.filter((p) => p.gap > 0 && p.is_blocked);
    if (filter === "decayed") rows = rows.filter((p) => p.is_decayed);
    if (search.trim()) {
      const needle = search.trim().toLowerCase();
      rows = rows.filter(
        (p) =>
          p.name.toLowerCase().includes(needle) ||
          p.code.toLowerCase().includes(needle) ||
          p.domain_name.toLowerCase().includes(needle),
      );
    }
    return rows;
  }, [positions.data, filter, search]);

  // Domains keep the order declared in the taxonomy (foundations first,
  // leadership last). Grouping by Map insertion order instead would put them
  // in whatever sequence the filter happened to produce, which reads as
  // random and makes the view hard to scan twice the same way.
  const domainOrdinal = useMemo(() => {
    const map = new Map<string, number>();
    for (const domain of graph.data?.domains ?? []) map.set(domain.name, domain.ordinal);
    return map;
  }, [graph.data]);

  const grouped = useMemo(() => {
    const map = new Map<string, SkillPosition[]>();
    for (const row of visible) {
      const list = map.get(row.domain_name) ?? [];
      list.push(row);
      map.set(row.domain_name, list);
    }
    for (const list of map.values()) {
      list.sort(
        (a, b) => b.blocks_below_target - a.blocks_below_target || a.code.localeCompare(b.code),
      );
    }
    return [...map.entries()].sort(
      ([a], [b]) => (domainOrdinal.get(a) ?? 99) - (domainOrdinal.get(b) ?? 99),
    );
  }, [visible, domainOrdinal]);

  const selected = selectedCode ? (byCode.get(selectedCode) ?? null) : null;

  if (positions.error) return <ErrorNote message={positions.error} onRetry={positions.reload} />;

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          {FILTERS.map((option) => (
            <button
              key={option.key}
              title={option.hint}
              onClick={() => setFilter(option.key)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${
                filter === option.key
                  ? "bg-slate-900 text-white ring-slate-900"
                  : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50"
              }`}
            >
              {option.label}
            </button>
          ))}
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Filter…"
            className="ml-auto w-40 rounded-md border border-slate-200 px-2 py-1 text-xs outline-none focus:border-sky-400"
          />
        </div>

        {positions.loading ? (
          <Loading what="skills" />
        ) : !grouped.length ? (
          <Empty>Nothing matches that filter.</Empty>
        ) : (
          <div className="space-y-4">
            {grouped.map(([domain, rows]) => (
              <Card key={domain} title={domain} subtitle={`${rows.length} skills`}>
                <ul className="divide-y divide-slate-100">
                  {rows.map((skill) => (
                    <li key={skill.code}>
                      <button
                        onClick={() => onSelect(skill.code)}
                        className={`flex w-full items-center gap-3 px-1 py-2 text-left hover:bg-slate-50 ${
                          selectedCode === skill.code ? "bg-sky-50" : ""
                        }`}
                      >
                        <span className="min-w-0 flex-1">
                          <span className="flex flex-wrap items-center gap-1.5">
                            <span className="truncate text-sm text-slate-800">{skill.name}</span>
                            {skill.is_decayed && <Badge tone="bad">decayed</Badge>}
                            {skill.gap > 0 && skill.is_blocked && <Badge tone="warn">blocked</Badge>}
                            {skill.is_available && <Badge tone="good">startable</Badge>}
                          </span>
                          <span className="mt-1 block font-mono text-[11px] text-slate-400">
                            {skill.code}
                          </span>
                        </span>
                        <LevelBar current={skill.current_level} target={skill.target_level} />
                        <span
                          className="w-8 shrink-0 text-right text-xs tabular-nums text-slate-500"
                          title="Wanted skills this one gates"
                        >
                          {skill.blocks_below_target || ""}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </Card>
            ))}
          </div>
        )}
      </div>

      <div className="lg:sticky lg:top-4 lg:self-start">
        {!selected ? (
          <Card title="Select a skill">
            <Empty>
              Pick a skill to see what it needs, what it unlocks, and whether anything is in the
              way.
            </Empty>
          </Card>
        ) : (
          <SkillDetail
            skill={selected}
            graph={graph.data}
            positions={byCode}
            onSelect={onSelect}
          />
        )}
      </div>
    </div>
  );
}

function SkillDetail({
  skill,
  graph,
  positions,
  onSelect,
}: {
  skill: SkillPosition;
  graph: ReturnType<typeof useApi<Awaited<ReturnType<typeof api.graph>>>>["data"];
  positions: Map<string, SkillPosition>;
  onSelect: (code: string) => void;
}) {
  return (
    <Card
      title={skill.name}
      subtitle={skill.domain_name}
      right={<LevelBar current={skill.current_level} target={skill.target_level} />}
    >
      <div className="space-y-4">
        {skill.description && <p className="text-sm text-slate-600">{skill.description}</p>}

        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
          <Row label="Level" value={`${skill.current_level} of a target of ${skill.target_level}`} />
          <Row label="Gates" value={`${skill.blocks_below_target} wanted skills`} />
          <Row label="Unlocks" value={`${skill.unlocks_total} downstream in total`} />
          <Row
            label="Last practised"
            value={
              skill.last_practised_on
                ? `${skill.last_practised_on} (${skill.months_since_practice}mo)`
                : "never recorded"
            }
            tone={skill.is_decayed ? "bad" : undefined}
          />
          <Row label="Decay window" value={`${skill.decay_months} months`} />
        </dl>

        {skill.unmet_prerequisites.length > 0 && (
          <div className="rounded-md border border-rose-200 bg-rose-50 p-3">
            <h3 className="text-xs font-semibold text-rose-900">
              Blocked by {skill.unmet_prerequisites.length} prerequisite
              {skill.unmet_prerequisites.length > 1 ? "s" : ""}
            </h3>
            <ul className="mt-1.5 space-y-1">
              {skill.unmet_prerequisites.map((prerequisite) => (
                <li key={prerequisite.code}>
                  <button
                    onClick={() => onSelect(prerequisite.code)}
                    className="text-left text-xs text-rose-900 underline decoration-rose-300 underline-offset-2 hover:decoration-rose-600"
                  >
                    {prerequisite.name} — at {prerequisite.current_level}, needs{" "}
                    {prerequisite.required_level}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {graph && (
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Neighbourhood
            </h3>
            <SkillNeighbourhood
              graph={graph}
              positions={positions}
              selected={skill}
              onSelect={onSelect}
            />
          </div>
        )}
      </div>
    </Card>
  );
}

function Row({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "bad";
}) {
  return (
    <div>
      <dt className="text-slate-500">{label}</dt>
      <dd className={tone === "bad" ? "font-medium text-rose-700" : "text-slate-800"}>{value}</dd>
    </div>
  );
}
