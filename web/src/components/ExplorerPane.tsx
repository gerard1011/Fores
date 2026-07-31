import { useQuery } from "@tanstack/react-query";
import { AlertCircle, Loader2 } from "lucide-react";
import {
  fetchGeographies,
  fetchLevels,
  fetchSeries,
  fetchSubcategories,
  RequestFailed,
} from "@/api/client";
import { AreaMultiSelect } from "./AreaMultiSelect";
import { LevelSelector, levelLabel } from "./LevelSelector";
import {
  AreaComparisonChart,
  ChartLegend,
  SeriesChart,
  toAreaRows,
  toRows,
} from "./SeriesChart";
import { SeriesTable } from "./SeriesTable";
import { SubcategoryCombobox } from "./SubcategoryCombobox";
import { humanise } from "@/lib/utils";
import { MAX_GEO_CODES } from "@/lib/constants";

export interface Selection {
  category: string;
  subcategory: string | null;
}

interface Props {
  level: string;
  geoCodes: string[];
  selection: Selection | null;
  onLevelChange: (level: string) => void;
  onGeoCodesChange: (geoCodes: string[]) => void;
  onSelect: (selection: Selection) => void;
}

export function ExplorerPane({
  level,
  geoCodes,
  selection,
  onLevelChange,
  onGeoCodesChange,
  onSelect,
}: Props) {
  const levels = useQuery({
    queryKey: ["levels"],
    queryFn: ({ signal }) => fetchLevels(signal),
    staleTime: Infinity,
  });

  // The area universe and the vocabulary are both scoped to the level.
  const geographies = useQuery({
    queryKey: ["geographies", level],
    queryFn: ({ signal }) => fetchGeographies(level, signal),
    staleTime: Infinity,
  });

  const index = useQuery({
    queryKey: ["subcategories", level],
    queryFn: ({ signal }) => fetchSubcategories(level, signal),
    staleTime: Infinity,
  });

  // Sorted so a different pick order produces the same cache key.
  const sortedCodes = [...geoCodes].sort();
  const series = useQuery({
    queryKey: ["series", level, selection?.category, sortedCodes],
    queryFn: ({ signal }) => fetchSeries(selection!.category, level, geoCodes, signal),
    enabled: !!selection?.category && geoCodes.length > 0,
    staleTime: 5 * 60 * 1000,
  });

  const comparing = geoCodes.length >= 2;
  // In comparison mode a single metric is shown across areas; fall back to the
  // first subcategory the series carries if none is explicitly chosen.
  const focusedSub =
    selection?.subcategory ?? series.data?.points[0]?.subcategory ?? null;

  return (
    <section
      aria-label="Explore the data"
      // min-w-0 for the same reason as ChatPane: grid items will not shrink
      // below their content without it, and the series table is wide.
      className="flex min-h-[26rem] min-w-0 flex-col rounded-lg border border-hairline bg-surface lg:min-h-0"
    >
      <header className="space-y-2 border-b border-hairline px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold">Explore</h2>
            <p className="text-xs text-ink-secondary">
              {selection
                ? humanise(selection.category)
                : `${levelLabel(level)}, across 2011, 2016 and 2021.`}
            </p>
          </div>
          {levels.data && (
            <LevelSelector
              levels={levels.data}
              value={level}
              onChange={(next) => {
                // Areas do not exist across levels, so a level switch clears them.
                onLevelChange(next);
                onGeoCodesChange([]);
              }}
            />
          )}
        </div>
        <AreaMultiSelect
          options={geographies.data ?? []}
          value={geoCodes}
          onChange={onGeoCodesChange}
          max={MAX_GEO_CODES}
        />
        <SubcategoryCombobox options={index.data ?? []} value={selection} onSelect={onSelect} />
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {(levels.isError || geographies.isError) && (
          <Failure error={levels.error ?? geographies.error} what="the area list" />
        )}
        {index.isError && <Failure error={index.error} what="the category list" />}

        {geoCodes.length === 0 && !geographies.isError && (
          <p className="py-8 text-center text-sm text-ink-muted">
            Choose one or more areas to explore, or ask a question — the answer's sources land
            here.
          </p>
        )}

        {geoCodes.length > 0 && !selection && (
          <p className="py-8 text-center text-sm text-ink-muted">
            Now pick a metric above to {comparing ? "compare across these areas" : "chart"}.
          </p>
        )}

        {geoCodes.length > 0 && selection && series.isPending && (
          <p className="flex items-center gap-2 py-8 text-sm text-ink-muted">
            <Loader2 aria-hidden className="size-4 animate-spin" />
            Loading {humanise(selection.category)}…
          </p>
        )}

        {geoCodes.length > 0 && selection && series.isError && (
          <Failure error={series.error} what={humanise(selection.category)} />
        )}

        {geoCodes.length > 0 && selection && series.data && (
          <div className="space-y-4">
            <ChartLegend years={series.data.years} />
            {comparing && focusedSub ? (
              <>
                <p className="text-xs text-ink-secondary">
                  Comparing <span className="font-medium text-ink">{focusedSub}</span> across{" "}
                  {series.data.geographies.length} areas.
                </p>
                <AreaComparisonChart series={series.data} subcategory={focusedSub} />
                <SeriesTable
                  rows={toAreaRows(series.data, focusedSub)}
                  years={series.data.years}
                  labelHeader="Area"
                  caption={`${focusedSub} by area and census year`}
                  highlighted={null}
                />
              </>
            ) : (
              <>
                <SeriesChart series={series.data} highlighted={selection.subcategory} />
                <SeriesTable
                  rows={toRows(series.data)}
                  years={series.data.years}
                  labelHeader="Subcategory"
                  caption={`${series.data.category} by subcategory and census year`}
                  highlighted={selection.subcategory}
                  onSelect={(subcategory) =>
                    onSelect({ category: selection.category, subcategory })
                  }
                />
              </>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function Failure({ error, what }: { error: unknown; what: string }) {
  const detail =
    error instanceof RequestFailed ? error.body.detail : `Could not load ${what}.`;
  return (
    <div
      role="alert"
      className="mb-3 flex items-start gap-2 rounded-md border border-critical/40 bg-critical/5 px-3 py-2 text-sm"
    >
      <AlertCircle aria-hidden className="mt-0.5 size-4 shrink-0 text-critical" />
      <p>{detail}</p>
    </div>
  );
}
