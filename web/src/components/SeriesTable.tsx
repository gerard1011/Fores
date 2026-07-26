import { ArrowDown, ArrowUp } from "lucide-react";
import { useMemo, useState } from "react";
import type { CategorySeries } from "@/api/client";
import { toRows } from "./SeriesChart";
import { cn, formatValue } from "@/lib/utils";

interface Props {
  series: CategorySeries;
  highlighted: string | null;
  onSelect: (subcategory: string) => void;
}

type SortKey = "subcategory" | number;

/**
 * The same data as a table.
 *
 * Not a fallback — it is the accessible reading of the chart and the exact
 * numbers you need when checking an answer, which a bar length cannot give you.
 */
export function SeriesTable({ series, highlighted, onSelect }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("subcategory");
  const [descending, setDescending] = useState(false);

  const rows = useMemo(() => {
    const data = toRows(series);
    const sorted = [...data].sort((a, b) => {
      if (sortKey === "subcategory") return a.subcategory.localeCompare(b.subcategory);
      return (a[sortKey] ?? 0) - (b[sortKey] ?? 0);
    });
    return descending ? sorted.reverse() : sorted;
  }, [series, sortKey, descending]);

  function sortBy(key: SortKey) {
    if (key === sortKey) {
      setDescending((d) => !d);
    } else {
      setSortKey(key);
      // Names read naturally A→Z; numbers are almost always wanted biggest first.
      setDescending(key !== "subcategory");
    }
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-xs">
        <caption className="sr-only">
          {series.category} by subcategory and census year
        </caption>
        <thead>
          <tr className="border-b border-hairline">
            <SortHeader
              label="Subcategory"
              active={sortKey === "subcategory"}
              descending={descending}
              onClick={() => sortBy("subcategory")}
              align="left"
            />
            {series.years.map((year) => (
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
          {rows.map((row) => {
            const selected = row.subcategory === highlighted;
            return (
              <tr
                key={row.subcategory}
                onClick={() => onSelect(row.subcategory)}
                className={cn(
                  "cursor-pointer border-b border-hairline/60 transition-colors hover:bg-wash",
                  selected && "bg-wash",
                )}
              >
                <td
                  className={cn(
                    "py-1.5 pr-2",
                    selected ? "font-semibold text-ink" : "text-ink-secondary",
                  )}
                >
                  {row.subcategory}
                </td>
                {series.years.map((year) => (
                  <td
                    key={year}
                    className="py-1.5 pl-2 text-right tabular-nums text-ink"
                  >
                    {row[year] == null ? "—" : formatValue(row[year])}
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
