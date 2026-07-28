import type { TornadoRow } from "../api/types";

/**
 * Tornado chart, hand-drawn in SVG.
 *
 * Recharts can be coaxed into this with a transparent stacked offset bar, but
 * the result fights the library on the two things that carry the meaning: the
 * zero line, and bars that must start and end at arbitrary values rather than
 * at an axis. Eighty lines of SVG is the smaller price.
 *
 * Each bar spans the NPV at the assumption's low bound to the NPV at its high
 * bound, everything else held at base. A bar crossing zero means the
 * recommendation itself changes within the stated range of that one
 * assumption — which is why zero is drawn heavier than the base line.
 */

const ROW_HEIGHT = 26;
const LABEL_WIDTH = 190;
const VALUE_WIDTH = 78;
const PADDING = 8;

export function Tornado({
  rows,
  baseNpv,
  currency,
  onSelect,
}: {
  rows: TornadoRow[];
  baseNpv: number;
  currency: string;
  onSelect?: (code: string) => void;
}) {
  const visible = rows.filter((row) => row.has_range);
  if (!visible.length) {
    return (
      <p className="py-6 text-center text-sm text-slate-400">
        No assumption in this model declares a range, so there is nothing to vary.
      </p>
    );
  }

  const values = visible.flatMap((row) => [Number(row.npv_at_low), Number(row.npv_at_high)]);
  const min = Math.min(...values, 0, baseNpv);
  const max = Math.max(...values, 0, baseNpv);
  const span = max - min || 1;

  const plotWidth = 460;
  const width = LABEL_WIDTH + plotWidth + VALUE_WIDTH;
  const height = visible.length * ROW_HEIGHT + 34;

  const x = (value: number) => LABEL_WIDTH + ((value - min) / span) * plotWidth;
  const zeroX = x(0);
  const baseX = x(baseNpv);

  const compact = (value: number) =>
    new Intl.NumberFormat("en-GB", {
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(value);

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${height}`} className="min-w-[720px] w-full" role="img">
        {/* Base NPV: where the model currently sits. */}
        <line
          x1={baseX}
          y1={4}
          x2={baseX}
          y2={height - 22}
          stroke="#94a3b8"
          strokeWidth={1}
          strokeDasharray="3 3"
        />
        {/* Zero: heavier, because crossing it changes the recommendation. */}
        <line x1={zeroX} y1={4} x2={zeroX} y2={height - 22} stroke="#0f172a" strokeWidth={1.5} />

        {visible.map((row, index) => {
          const low = Number(row.npv_at_low);
          const high = Number(row.npv_at_high);
          const left = Math.min(low, high);
          const right = Math.max(low, high);
          const y = index * ROW_HEIGHT + PADDING;
          const barX = x(left);
          const barWidth = Math.max(2, x(right) - barX);

          return (
            <g
              key={row.code}
              onClick={() => onSelect?.(row.code)}
              style={{ cursor: onSelect ? "pointer" : "default" }}
            >
              <rect
                x={0}
                y={y - 2}
                width={width}
                height={ROW_HEIGHT - 4}
                fill={index % 2 ? "#f8fafc" : "transparent"}
              />
              <text
                x={LABEL_WIDTH - 8}
                y={y + 13}
                textAnchor="end"
                fontSize={10.5}
                fill={row.flips_the_decision ? "#9f1239" : "#334155"}
                fontFamily="ui-monospace, monospace"
              >
                {row.code.length > 26 ? `${row.code.slice(0, 25)}…` : row.code}
              </text>

              <rect
                x={barX}
                y={y + 3}
                width={barWidth}
                height={ROW_HEIGHT - 14}
                rx={2}
                fill={row.flips_the_decision ? "#fb7185" : "#0284c7"}
                opacity={row.confidence === "low" ? 1 : 0.72}
              />
              {row.confidence === "low" && (
                <title>{`${row.label} — low confidence`}</title>
              )}

              <text
                x={LABEL_WIDTH + plotWidth + 8}
                y={y + 13}
                fontSize={10}
                fill="#475569"
                fontFamily="ui-monospace, monospace"
              >
                ±{compact(Number(row.swing) / 2)}
              </text>
            </g>
          );
        })}

        <text x={zeroX} y={height - 8} fontSize={9.5} textAnchor="middle" fill="#0f172a">
          0
        </text>
        <text x={baseX} y={height - 8} fontSize={9.5} textAnchor="middle" fill="#64748b">
          base {compact(baseNpv)}
        </text>
        <text x={LABEL_WIDTH} y={height - 8} fontSize={9} fill="#94a3b8">
          NPV ({currency})
        </text>
      </svg>

      <p className="mt-1 text-xs text-slate-500">
        Each bar is the NPV across that assumption&rsquo;s stated range, everything else held at
        base. Solid fill marks a low-confidence assumption; red marks one whose range crosses
        zero — within its own stated bounds, the recommendation changes.
      </p>
    </div>
  );
}
