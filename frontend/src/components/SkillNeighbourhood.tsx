import type { Graph, SkillPosition } from "../api/types";

/**
 * The graph, one neighbourhood at a time.
 *
 * A force-directed layout of 83 nodes and 111 edges is a hairball: it looks
 * like a graph and answers no question. What a person actually needs to know
 * standing in front of one skill is "what does this need" and "what does this
 * unlock", so that is what this draws — direct prerequisites on the left, the
 * skill in the middle, direct dependents on the right.
 *
 * Prerequisites are coloured by whether they are satisfied, which turns the
 * picture into the answer to "why can I not start this yet".
 */

const MAX_PER_SIDE = 7;
const ROW = 30;
const NODE_W = 176;
const NODE_H = 22;
const COL_GAP = 56;

export function SkillNeighbourhood({
  graph,
  positions,
  selected,
  onSelect,
}: {
  graph: Graph;
  positions: Map<string, SkillPosition>;
  selected: SkillPosition;
  onSelect: (code: string) => void;
}) {
  const byId = new Map(graph.skills.map((s) => [s.id, s]));

  const prerequisites = graph.edges
    .filter((e) => e.dependent_skill_id === selected.skill_id)
    .map((e) => ({ node: byId.get(e.prerequisite_skill_id), required: e.required_level }))
    .filter((x): x is { node: NonNullable<typeof x.node>; required: number } => !!x.node);

  const dependents = graph.edges
    .filter((e) => e.prerequisite_skill_id === selected.skill_id)
    .map((e) => ({ node: byId.get(e.dependent_skill_id), required: e.required_level }))
    .filter((x): x is { node: NonNullable<typeof x.node>; required: number } => !!x.node);

  const left = prerequisites.slice(0, MAX_PER_SIDE);
  const right = dependents.slice(0, MAX_PER_SIDE);
  const rows = Math.max(left.length, right.length, 1);
  const height = rows * ROW + 24;
  const width = NODE_W * 3 + COL_GAP * 2;
  const midY = height / 2;

  const columnY = (index: number, count: number) =>
    midY - ((count - 1) * ROW) / 2 + index * ROW;

  const centreX = NODE_W + COL_GAP;
  const rightX = centreX + NODE_W + COL_GAP;

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="min-w-[560px] w-full"
        role="img"
        aria-label={`Prerequisites and dependents of ${selected.name}`}
      >
        {left.map((item, index) => {
          const y = columnY(index, left.length);
          const satisfied = (positions.get(item.node.code)?.current_level ?? 0) >= item.required;
          return (
            <g key={`p-${item.node.id}`}>
              <path
                d={`M ${NODE_W} ${y} C ${NODE_W + COL_GAP / 2} ${y}, ${centreX - COL_GAP / 2} ${midY}, ${centreX} ${midY}`}
                fill="none"
                stroke={satisfied ? "#94a3b8" : "#fb7185"}
                strokeWidth={satisfied ? 1 : 1.75}
                strokeDasharray={satisfied ? undefined : "4 3"}
              />
              <NodeBox
                x={0}
                y={y}
                label={item.node.code}
                sub={`needs ${item.required}`}
                tone={satisfied ? "ok" : "blocking"}
                onClick={() => onSelect(item.node.code)}
              />
            </g>
          );
        })}

        {right.map((item, index) => {
          const y = columnY(index, right.length);
          const unlocked = selected.current_level >= item.required;
          return (
            <g key={`d-${item.node.id}`}>
              <path
                d={`M ${centreX + NODE_W} ${midY} C ${centreX + NODE_W + COL_GAP / 2} ${midY}, ${rightX - COL_GAP / 2} ${y}, ${rightX} ${y}`}
                fill="none"
                stroke={unlocked ? "#34d399" : "#cbd5e1"}
                strokeWidth={1}
              />
              <NodeBox
                x={rightX}
                y={y}
                label={item.node.code}
                sub={unlocked ? "unlocked" : `wants ${item.required}`}
                tone={unlocked ? "unlocked" : "muted"}
                onClick={() => onSelect(item.node.code)}
              />
            </g>
          );
        })}

        <NodeBox
          x={centreX}
          y={midY}
          label={selected.code}
          sub={`level ${selected.current_level} / target ${selected.target_level}`}
          tone="selected"
        />
      </svg>

      {(prerequisites.length > MAX_PER_SIDE || dependents.length > MAX_PER_SIDE) && (
        <p className="mt-1 text-center text-xs text-slate-400">
          Showing {left.length} of {prerequisites.length} prerequisites and {right.length} of{" "}
          {dependents.length} dependents.
        </p>
      )}
      {prerequisites.length === 0 && dependents.length === 0 && (
        <p className="mt-1 text-center text-xs text-slate-400">
          Isolated in the taxonomy: no prerequisites and nothing depends on it.
        </p>
      )}
    </div>
  );
}

function NodeBox({
  x,
  y,
  label,
  sub,
  tone,
  onClick,
}: {
  x: number;
  y: number;
  label: string;
  sub: string;
  tone: "ok" | "blocking" | "unlocked" | "muted" | "selected";
  onClick?: () => void;
}) {
  const tones = {
    ok: { fill: "#f8fafc", stroke: "#cbd5e1", text: "#334155" },
    blocking: { fill: "#fff1f2", stroke: "#fda4af", text: "#9f1239" },
    unlocked: { fill: "#ecfdf5", stroke: "#6ee7b7", text: "#065f46" },
    muted: { fill: "#f8fafc", stroke: "#e2e8f0", text: "#64748b" },
    selected: { fill: "#0f172a", stroke: "#0f172a", text: "#f8fafc" },
  } as const;
  const t = tones[tone];
  return (
    <g
      transform={`translate(${x}, ${y - NODE_H / 2})`}
      onClick={onClick}
      style={{ cursor: onClick ? "pointer" : "default" }}
    >
      <rect
        width={NODE_W}
        height={NODE_H}
        rx={4}
        fill={t.fill}
        stroke={t.stroke}
        strokeWidth={1}
      />
      <text x={7} y={14} fontSize={10.5} fontFamily="ui-monospace, monospace" fill={t.text}>
        {label.length > 24 ? `${label.slice(0, 23)}…` : label}
      </text>
      <text x={NODE_W - 7} y={14} fontSize={9} textAnchor="end" fill={t.text} opacity={0.75}>
        {sub}
      </text>
    </g>
  );
}
