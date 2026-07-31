import { ArrowDown, ArrowUp } from "lucide-react";
import { useMemo, useState } from "react";
import type { ChartRow } from "./SeriesChart";
import { cn, formatValue } from "@/lib/utils";

interface Props {
  rows: ChartRow[];
  years: number[];
  /** Header for the first column: "Subcategory" or "Area". */
  labelHeader: string;
  caption: string;
  highlighted: string | null;
  onSelect?: (label: string) => void;
}

type SortKey = "label" | number;

/**
 * The same data as a table.
 *
 * Not a fallback — it is the accessible reading of the chart and the exact
 * numbers you need when checking an answer, which a bar length cannot give you.
 * Drives both the single-area (rows = subcategories) and comparison
 * (rows = areas) views; the caller decides what a row is.
 */
export function SeriesTable({ rows, years, labelHeader, caption, highlighted, onSelect }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("label");
  const [descending, setDescending] = useState(false);

  const sorted = useMemo(() => {
    const data = [...rows].sort((a, b) => {
      if (sortKey === "label") return a.label.localeCompare(b.label);
      return (Number(a[sortKey] ?? 0)) - (Number(b[sortKey] ?? 0));
    });
    return descending ? data.reverse() : data;
  }, [rows, sortKey, descending]);

  function sortBy(key: SortKey) {
    if (key === sortKey) {
      setDescending((d) => !d);
    } else {
      setSortKey(key);
      // Names read naturally A→Z; numbers are almost always wanted biggest first.
      setDescending(key !== "label");
    }
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-xs">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-hairline">
            <SortHeader
              label={labelHeader}
              active={sortKey === "label"}
              descending={descending}
              onClick={() => sortBy("label")}
              align="left"
            />
            {years.map((year) => (
              <SortHeader
                key={year}
                label={String(year)}
                active={sortKey === year}
                descending={descending}
                onClick={() => sortBy(year)}
                align="right"
              />
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => {
            const selected = row.label === highlighted;
            return (
              <tr
                key={row.label}
                onClick={onSelect ? () => onSelect(row.label) : undefined}
                className={cn(
                  "border-b border-hairline/60 transition-colors",
                  onSelect && "cursor-pointer hover:bg-wash",
                  selected && "bg-wash",
                )}
              >
                <td
                  className={cn(
                    "py-1.5 pr-2",
                    selected ? "font-semibold text-ink" : "text-ink-secondary",
                  )}
                >
                  {row.label}
                </td>
                {years.map((year) => (
                  <td key={year} className="py-1.5 pl-2 text-right tabular-nums text-ink">
                    {row[year] == null ? "—" : formatValue(Number(row[year]))}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function SortHeader({
  label,
  active,
  descending,
  onClick,
  align,
}: {
  label: string;
  active: boolean;
  descending: boolean;
  onClick: () => void;
  align: "left" | "right";
}) {
  const Icon = descending ? ArrowDown : ArrowUp;
  return (
    <th
      scope="col"
      aria-sort={active ? (descending ? "descending" : "ascending") : "none"}
      className={cn("py-1.5", align === "right" ? "pl-2 text-right" : "pr-2 text-left")}
    >
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "inline-flex items-center gap-1 font-medium",
          active ? "text-ink" : "text-ink-muted hover:text-ink-secondary",
        )}
      >
        {align === "right" && active && <Icon aria-hidden className="size-3" />}
        {label}
        {align === "left" && active && <Icon aria-hidden className="size-3" />}
      </button>
    </th>
  );
}
