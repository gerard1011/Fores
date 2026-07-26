import * as Popover from "@radix-ui/react-popover";
import { Command } from "cmdk";
import { Check, ChevronsUpDown, Search } from "lucide-react";
import { useMemo, useState } from "react";
import type { SubcategoryRef } from "@/api/client";
import { cn, humanise } from "@/lib/utils";

interface Props {
  options: SubcategoryRef[];
  value: { category: string; subcategory: string | null } | null;
  onSelect: (selection: { category: string; subcategory: string }) => void;
}

/**
 * Search across every subcategory, grouped by category.
 *
 * A native select over 262 options is unusable, and picking a category first
 * assumes you already know which of the 31 contains the thing you want —
 * "separate house" is discoverable here without knowing it lives under
 * dwelling_structure.
 */
export function SubcategoryCombobox({ options, value, onSelect }: Props) {
  const [open, setOpen] = useState(false);

  const grouped = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const option of options) {
      const list = map.get(option.category) ?? [];
      list.push(option.subcategory);
      map.set(option.category, list);
    }
    return [...map.entries()];
  }, [options]);

  const label = value
    ? value.subcategory
      ? `${humanise(value.category)} → ${value.subcategory}`
      : humanise(value.category)
    : "Search the data…";

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger
        className={cn(
          "flex w-full items-center gap-2 rounded-md border border-hairline bg-page px-3 py-2 text-left text-sm",
          "hover:bg-wash focus-visible:outline-2 focus-visible:outline-accent",
        )}
        aria-label="Choose a category or subcategory"
      >
        <Search aria-hidden className="size-3.5 shrink-0 text-ink-muted" />
        <span className={cn("flex-1 truncate", !value && "text-ink-muted")}>{label}</span>
        <ChevronsUpDown aria-hidden className="size-3.5 shrink-0 text-ink-muted" />
      </Popover.Trigger>

      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={4}
          className="z-50 w-[var(--radix-popover-trigger-width)] overflow-hidden rounded-md border border-hairline bg-surface shadow-lg"
        >
          <Command
            // Names are lowercase DB values; humanised category headings are
            // display-only, so search both the raw and the humanised form.
            filter={(itemValue, search) =>
              itemValue.toLowerCase().includes(search.toLowerCase()) ? 1 : 0
            }
          >
            <div className="flex items-center gap-2 border-b border-hairline px-3">
              <Search aria-hidden className="size-3.5 shrink-0 text-ink-muted" />
              <Command.Input
                autoFocus
                placeholder="Search 262 subcategories…"
                className="h-9 flex-1 bg-transparent text-sm outline-none placeholder:text-ink-muted"
              />
            </div>

            <Command.List className="max-h-72 overflow-y-auto p-1">
              <Command.Empty className="px-3 py-6 text-center text-sm text-ink-muted">
                Nothing matches that.
              </Command.Empty>

              {grouped.map(([category, subs]) => (
                <Command.Group
                  key={category}
                  heading={
                    <span className="px-2 text-xs font-medium text-ink-muted">
                      {humanise(category)}
                    </span>
                  }
                >
                  {subs.map((subcategory) => {
                    const selected =
                      value?.category === category && value?.subcategory === subcategory;
                    return (
                      <Command.Item
                        key={`${category}/${subcategory}`}
                        value={`${humanise(category)} ${category} ${subcategory}`}
                        onSelect={() => {
                          onSelect({ category, subcategory });
                          setOpen(false);
                        }}
                        className={cn(
                          "flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm",
                          "data-[selected=true]:bg-wash",
                        )}
                      >
                        <Check
                          aria-hidden
                          className={cn("size-3.5 shrink-0", !selected && "opacity-0")}
                        />
                        <span className="truncate">{subcategory}</span>
                      </Command.Item>
                    );
                  })}
                </Command.Group>
              ))}
            </Command.List>
          </Command>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
