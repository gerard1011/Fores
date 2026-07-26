import { useQuery } from "@tanstack/react-query";
import { AlertCircle, Loader2 } from "lucide-react";
import { fetchSeries, fetchSubcategories, RequestFailed } from "@/api/client";
import { ChartLegend, SeriesChart } from "./SeriesChart";
import { SeriesTable } from "./SeriesTable";
import { SubcategoryCombobox } from "./SubcategoryCombobox";
import { humanise } from "@/lib/utils";

export interface Selection {
  category: string;
  subcategory: string | null;
}

interface Props {
  selection: Selection | null;
  onSelect: (selection: Selection) => void;
}

export function ExplorerPane({ selection, onSelect }: Props) {
  // Names only and small, so it is fetched once and cached indefinitely.
  const index = useQuery({
    queryKey: ["subcategories"],
    queryFn: ({ signal }) => fetchSubcategories(signal),
    staleTime: Infinity,
  });

  // Cached per category, so revisiting one the chat already cited is instant.
  const series = useQuery({
    queryKey: ["series", selection?.category],
    queryFn: ({ signal }) => fetchSeries(selection!.category, signal),
    enabled: !!selection?.category,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <section
      aria-label="Explore the data"
      // min-w-0 for the same reason as ChatPane: grid items will not shrink
      // below their content without it, and the series table is wide.
      className="flex min-h-[26rem] min-w-0 flex-col rounded-lg border border-hairline bg-surface lg:min-h-0"
    >
      <header className="space-y-2 border-b border-hairline px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold">Explore</h2>
          <p className="text-xs text-ink-secondary">
            {selection
              ? humanise(selection.category)
              : "Every category, across 2011, 2016 and 2021."}
          </p>
        </div>
        <SubcategoryCombobox
          options={index.data ?? []}
          value={selection}
          onSelect={onSelect}
        />
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {index.isError && <Failure error={index.error} what="the category list" />}

        {!selection && !index.isError && (
          <p className="py-8 text-center text-sm text-ink-muted">
            Search above, or ask a question — the answer's sources land here.
          </p>
        )}

        {selection && series.isPending && (
          <p className="flex items-center gap-2 py-8 text-sm text-ink-muted">
            <Loader2 aria-hidden className="size-4 animate-spin" />
            Loading {humanise(selection.category)}…
          </p>
        )}

        {selection && series.isError && (
          <Failure error={series.error} what={humanise(selection.category)} />
        )}

        {selection && series.data && (
          <div className="space-y-4">
            <ChartLegend years={series.data.years} />
            <SeriesChart
              series={series.data}
              highlighted={selection.subcategory}
            />
            <SeriesTable
              series={series.data}
              highlighted={selection.subcategory}
              onSelect={(subcategory) =>
                onSelect({ category: selection.category, subcategory })
              }
            />
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
      className="flex items-start gap-2 rounded-md border border-critical/40 bg-critical/5 px-3 py-2 text-sm"
    >
      <AlertCircle aria-hidden className="mt-0.5 size-4 shrink-0 text-critical" />
      <p>{detail}</p>
    </div>
  );
}
