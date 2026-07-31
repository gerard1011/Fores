import type { Level } from "@/api/client";
import { cn } from "@/lib/utils";

/** Friendly labels for the two granularities the data carries. */
const LABELS: Record<string, string> = {
  LGA: "Local areas",
  STE: "States & territories",
};

export function levelLabel(level: string): string {
  return LABELS[level] ?? level;
}

interface Props {
  levels: Level[];
  value: string;
  onChange: (level: string) => void;
}

/**
 * Segmented control choosing the geography granularity.
 *
 * Top-level because it reframes everything below it: switching level swaps the
 * whole area universe (and, in principle, the vocabulary), so the areas chosen
 * at one level cannot carry over to the other.
 */
export function LevelSelector({ levels, value, onChange }: Props) {
  return (
    <div
      role="radiogroup"
      aria-label="Geography level"
      className="inline-flex rounded-md border border-hairline bg-page p-0.5"
    >
      {levels.map((level) => {
        const active = level.level === value;
        return (
          <button
            key={level.level}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(level.level)}
            className={cn(
              "rounded px-2.5 py-1 text-xs font-medium transition-colors",
              "focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent",
              active ? "bg-surface text-ink shadow-sm" : "text-ink-muted hover:text-ink-secondary",
            )}
          >
            {levelLabel(level.level)}
            <span className="ml-1 tabular-nums text-ink-muted">({level.area_count})</span>
          </button>
        );
      })}
    </div>
  );
}
