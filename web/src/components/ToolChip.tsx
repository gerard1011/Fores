import * as Collapsible from "@radix-ui/react-collapsible";
import { AlertTriangle, ChevronRight, Database, Loader2, MapPin, Sigma } from "lucide-react";
import { useState } from "react";
import type { QueryCensusInput } from "@/api/events";
import type { ToolStep } from "@/hooks/useChat";
import { cn, formatValue, humanise } from "@/lib/utils";

/** A census citation, when the step is one. Drives the explorer selection. */
export interface Citation {
  category: string;
  subcategory: string;
  level: string;
  geoCodes: string[];
}

export function citationOf(step: ToolStep): Citation | null {
  if (step.name !== "query_census") return null;
  const input = step.input as Partial<QueryCensusInput>;
  const { category, subcategory, level, geo_codes } = input;
  if (typeof category !== "string" || typeof subcategory !== "string") return null;
  if (typeof level !== "string") return null;
  if (!Array.isArray(geo_codes) || geo_codes.some((c) => typeof c !== "string")) return null;
  return { category, subcategory, level, geoCodes: geo_codes };
}

function summarise(step: ToolStep): string {
  const citation = citationOf(step);
  if (citation) {
    const areas =
      citation.geoCodes.length === 1
        ? "1 area"
        : `${citation.geoCodes.length} areas`;
    return `Queried ${humanise(citation.category)} → ${citation.subcategory} (${areas})`;
  }
  if (step.name === "find_geography") {
    const q = typeof step.input.name_query === "string" ? step.input.name_query : "";
    return q ? `Looked up "${q}"` : "Looked up an area";
  }
  if (step.name === "calculate_change") {
    const { value_start, value_end } = step.input;
    if (typeof value_start === "number" && typeof value_end === "number") {
      return `Calculated change ${formatValue(value_start)} → ${formatValue(value_end)}`;
    }
    return "Calculated change";
  }
  return step.name;
}

interface Props {
  step: ToolStep;
  onSelect?: (citation: Citation) => void;
}

/**
 * One tool call, collapsed to a single line.
 *
 * Expanding shows the raw input and output — the point of this app is
 * verifying the model's answers, so the evidence stays reachable rather than
 * vanishing once the answer arrives.
 */
export function ToolChip({ step, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const citation = citationOf(step);
  const pending = !step.result;
  const failed = step.result?.isError ?? false;

  const Icon = failed
    ? AlertTriangle
    : pending
      ? Loader2
      : step.name === "query_census"
        ? Database
        : step.name === "find_geography"
          ? MapPin
          : Sigma;

  return (
    <Collapsible.Root
      open={open}
      onOpenChange={setOpen}
      className="rounded-md border border-hairline bg-wash/40"
    >
      <Collapsible.Trigger
        onClick={() => citation && onSelect?.(citation)}
        className={cn(
          "flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-xs",
          "text-ink-secondary transition-colors hover:bg-wash",
          "focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent",
        )}
        // Screen readers get told about the second effect of this click, which
        // is otherwise only discoverable by watching the other pane move.
        aria-label={
          citation
            ? `${summarise(step)}. Expand details and show this in the explorer.`
            : `${summarise(step)}. Expand details.`
        }
      >
        <ChevronRight
          aria-hidden
          className={cn("size-3.5 shrink-0 transition-transform", open && "rotate-90")}
        />
        <Icon
          aria-hidden
          className={cn(
            "size-3.5 shrink-0",
            failed && "text-critical",
            pending && "animate-spin",
          )}
        />
        <span className="truncate">{summarise(step)}</span>
      </Collapsible.Trigger>

      <Collapsible.Content>
        <div className="space-y-2 border-t border-hairline px-2.5 py-2 text-xs">
          <Field label="Input" value={JSON.stringify(step.input, null, 2)} />
          {step.result && (
            <Field
              label={failed ? "Error" : "Result"}
              value={step.result.content}
              tone={failed ? "critical" : undefined}
            />
          )}
        </div>
      </Collapsible.Content>
    </Collapsible.Root>
  );
}

function Field({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "critical";
}) {
  return (
    <div>
      <div className="mb-0.5 font-medium text-ink-muted">{label}</div>
      <pre
        className={cn(
          "overflow-x-auto rounded bg-wash p-2 font-mono text-[11px] leading-relaxed",
          tone === "critical" ? "text-critical" : "text-ink-secondary",
        )}
      >
        {value}
      </pre>
    </div>
  );
}
