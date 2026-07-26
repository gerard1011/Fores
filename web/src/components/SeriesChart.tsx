import {
  Bar,
  BarChart,
  Cell,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CategorySeries } from "@/api/client";
import { formatValue } from "@/lib/utils";

/** Ordinal ramp: one hue, light to dark, because years are ordered. */
const YEAR_COLOR: Record<number, string> = {
  2011: "var(--year-2011)",
  2016: "var(--year-2016)",
  2021: "var(--year-2021)",
};

const AXIS = "var(--text-muted)";
const ROW_HEIGHT = 34;

export interface ChartRow {
  subcategory: string;
  [year: number]: number;
}

export function toRows(series: CategorySeries): ChartRow[] {
  const rows = new Map<string, ChartRow>();
  for (const point of series.points) {
    const row = rows.get(point.subcategory) ?? { subcategory: point.subcategory };
    row[point.year] = point.value;
    rows.set(point.subcategory, row);
  }
  return [...rows.values()];
}

interface Props {
  series: CategorySeries;
  highlighted: string | null;
}

/**
 * A whole category across every census year.
 *
 * Horizontal bars because subcategory labels are long ("semi-detached, row or
 * terrace house") and there can be 35 of them — vertical bars would give
 * rotated, unreadable ticks. The plot grows with the row count and scrolls
 * inside its own container rather than squashing.
 *
 * A highlighted subcategory is emphasised with opacity, not a different
 * colour: hue encodes the year, and repainting one row would break that.
 */
export function SeriesChart({ series, highlighted }: Props) {
  const rows = toRows(series);
  const height = Math.max(200, rows.length * ROW_HEIGHT + 48);

  return (
    <div className="overflow-y-auto" style={{ maxHeight: "min(60vh, 520px)" }}>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart
          data={rows}
          layout="vertical"
          margin={{ top: 4, right: 16, bottom: 4, left: 4 }}
          barGap={2}
          barCategoryGap="22%"
        >
          <CartesianGrid horizontal={false} stroke="var(--gridline)" />
          <XAxis
            type="number"
            tickFormatter={formatValue}
            stroke={AXIS}
            tick={{ fill: AXIS, fontSize: 11 }}
            axisLine={{ stroke: "var(--baseline)" }}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="subcategory"
            width={150}
            stroke={AXIS}
            tickLine={false}
            axisLine={{ stroke: "var(--baseline)" }}
            tick={(props) => <SubcategoryTick {...props} highlighted={highlighted} />}
          />
          <Tooltip
            cursor={{ fill: "var(--wash)" }}
            content={({ active, payload, label }) =>
              active && payload?.length ? (
                <TooltipCard label={String(label)} payload={payload} />
              ) : null
            }
          />
          {series.years.map((year) => (
            <Bar
              key={year}
              dataKey={year}
              name={String(year)}
              fill={YEAR_COLOR[year] ?? "var(--year-2016)"}
              radius={[0, 4, 4, 0]}
              isAnimationActive={false}
            >
              {rows.map((row) => (
                <Cell
                  key={row.subcategory}
                  fillOpacity={
                    !highlighted || row.subcategory === highlighted ? 1 : 0.3
                  }
                />
              ))}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Legend lives outside the scroll container so it stays visible. */
export function ChartLegend({ years }: { years: number[] }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1">
      {years.map((year) => (
        <li key={year} className="flex items-center gap-1.5 text-xs text-ink-secondary">
          <span
            aria-hidden
            className="size-2.5 rounded-sm"
            style={{ background: YEAR_COLOR[year] }}
          />
          <span className="tabular-nums">{year}</span>
        </li>
      ))}
    </ul>
  );
}

// Recharts types its tick coordinates as string | number, so this takes them
// loosely and narrows here rather than fighting the upstream signature.
function SubcategoryTick(props: {
  x?: string | number;
  y?: string | number;
  payload?: { value?: string };
  highlighted: string | null;
}) {
  const { payload, highlighted } = props;
  const x = Number(props.x ?? 0);
  const y = Number(props.y ?? 0);
  const value = payload?.value ?? "";
  const isHighlighted = value === highlighted;
  const display = value.length > 24 ? `${value.slice(0, 23)}…` : value;

  return (
    <text
      x={x - 6}
      y={y}
      dy={4}
      textAnchor="end"
      fontSize={11}
      fontWeight={isHighlighted ? 600 : 400}
      fill={isHighlighted ? "var(--text-primary)" : AXIS}
    >
      <title>{value}</title>
      {display}
    </text>
  );
}

function TooltipCard({
  label,
  payload,
}: {
  label: string;
  payload: readonly { name?: string | number; value?: unknown; color?: string }[];
}) {
  const first = Number(payload[0]?.value);
  const last = Number(payload[payload.length - 1]?.value);
  const change =
    payload.length > 1 && Number.isFinite(first) && Number.isFinite(last) && first !== 0
      ? ((last - first) / first) * 100
      : null;

  return (
    <div className="rounded-md border border-hairline bg-surface px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 font-medium text-ink">{label}</div>
      <table className="tabular-nums">
        <tbody>
          {payload.map((entry) => (
            <tr key={String(entry.name)}>
              <td className="pr-2">
                <span
                  aria-hidden
                  className="mr-1.5 inline-block size-2 rounded-sm align-middle"
                  style={{ background: entry.color }}
                />
                <span className="text-ink-secondary">{entry.name}</span>
              </td>
              <td className="text-right text-ink">{formatValue(Number(entry.value))}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {change !== null && (
        <div className="mt-1 border-t border-hairline pt-1 text-ink-secondary">
          {change >= 0 ? "+" : ""}
          {change.toFixed(1)}% over the period
        </div>
      )}
    </div>
  );
}
