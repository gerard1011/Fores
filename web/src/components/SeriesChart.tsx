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

/** A chart row: a label (subcategory or area) and one value per year. */
export interface ChartRow {
  label: string;
  [year: number]: number | string;
}

function group(points: CategorySeries["points"], keyOf: (p: CategorySeries["points"][number]) => string, seed: string[] = []): ChartRow[] {
  const rows = new Map<string, ChartRow>();
  // Seed with labels that must appear even when they have no points (an area
  // with no data for the chosen subcategory), so a gap reads as "—" not absence.
  for (const label of seed) rows.set(label, { label });
  for (const point of points) {
    const key = keyOf(point);
    const row = rows.get(key) ?? { label: key };
    row[point.year] = point.value;
    rows.set(key, row);
  }
  return [...rows.values()];
}

/** One row per subcategory — the single-area view. */
export function toRows(series: CategorySeries): ChartRow[] {
  return group(series.points, (p) => p.subcategory);
}

/** One row per area for a single subcategory — the comparison view. */
export function toAreaRows(series: CategorySeries, subcategory: string): ChartRow[] {
  const seed = series.geographies.map((g) => g.geo_name);
  const points = series.points.filter((p) => p.subcategory === subcategory);
  return group(points, (p) => p.geo_name, seed);
}

interface BarsProps {
  rows: ChartRow[];
  years: number[];
  /** A label to emphasise, or null. Used only in the subcategory view. */
  highlighted: string | null;
  labelWidth: number;
}

/**
 * Horizontal year-coloured bars, one group per row.
 *
 * Horizontal because labels are long (a subcategory like "semi-detached, row or
 * terrace house", or a canonical area name) and there can be many — vertical
 * bars would give rotated, unreadable ticks. Hue encodes the year in both
 * views, so a highlighted row is dimmed by opacity rather than recoloured.
 */
function YearBars({ rows, years, highlighted, labelWidth }: BarsProps) {
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
            dataKey="label"
            width={labelWidth}
            stroke={AXIS}
            tickLine={false}
            axisLine={{ stroke: "var(--baseline)" }}
            tick={(props) => <LabelTick {...props} highlighted={highlighted} />}
          />
          <Tooltip
            cursor={{ fill: "var(--wash)" }}
            content={({ active, payload, label }) =>
              active && payload?.length ? (
                <TooltipCard label={String(label)} payload={payload} />
              ) : null
            }
          />
          {years.map((year) => (
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
                  key={row.label}
                  fillOpacity={!highlighted || row.label === highlighted ? 1 : 0.3}
                />
              ))}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

interface Props {
  series: CategorySeries;
  highlighted: string | null;
}

/** A whole category across every census year, for a single area. */
export function SeriesChart({ series, highlighted }: Props) {
  return (
    <YearBars rows={toRows(series)} years={series.years} highlighted={highlighted} labelWidth={150} />
  );
}

/** One subcategory across every census year, compared across areas. */
export function AreaComparisonChart({
  series,
  subcategory,
}: {
  series: CategorySeries;
  subcategory: string;
}) {
  return (
    <YearBars
      rows={toAreaRows(series, subcategory)}
      years={series.years}
      highlighted={null}
      labelWidth={170}
    />
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
function LabelTick(props: {
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
