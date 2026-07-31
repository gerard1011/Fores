import * as Popover from "@radix-ui/react-popover";
import { Command } from "cmdk";
import { Check, ChevronsUpDown, MapPin, X } from "lucide-react";
import { useMemo, useState } from "react";
import type { Geography } from "@/api/client";
import { cn } from "@/lib/utils";

interface Props {
  options: Geography[];
  /** Selected geo_codes. */
  value: string[];
  onChange: (geoCodes: string[]) => void;
  max: number;
}

/**
 * Search-and-pick multiple areas by canonical name.
 *
 * A flat list of 565 LGAs is only navigable by typing, so this is a search box
 * first. Selected areas show as removable chips; the picker caps at `max` to
 * bound the query, the legend, and the agent's token budget alike.
 */
export function AreaMultiSelect({ options, value, onChange, max }: Props) {
  const [open, setOpen] = useState(false);

  const nameOf = useMemo(() => {
    const map = new Map(options.map((o) => [o.geo_code, o.geo_name]));
    return (code: string) => map.get(code) ?? code;
  }, [options]);

  const atCap = value.length >= max;

  function toggle(code: string) {
    if (value.includes(code)) {
      onChange(value.filter((c) => c !== code));
    } else if (!atCap) {
      onChange([...value, code]);
    }
  }

  return (
    <div className="space-y-2">
      <Popover.Root open={open} onOpenChange={setOpen}>
        <Popover.Trigger
          className={cn(
            "flex w-full items-center gap-2 rounded-md border border-hairline bg-page px-3 py-2 text-left text-sm",
            "hover:bg-wash focus-visible:outline-2 focus-visible:outline-accent",
          )}
          aria-label="Choose areas to compare"
        >
          <MapPin aria-hidden className="size-3.5 shrink-0 text-ink-muted" />
          <span className={cn("flex-1 truncate", value.length === 0 && "text-ink-muted")}>
            {value.length === 0
              ? "Choose areas…"
              : `${value.length} area${value.length > 1 ? "s" : ""} selected`}
          </span>
          <ChevronsUpDown aria-hidden className="size-3.5 shrink-0 text-ink-muted" />
        </Popover.Trigger>

        <Popover.Portal>
          <Popover.Content
            align="start"
            sideOffset={4}
            className="z-50 w-[var(--radix-popover-trigger-width)] overflow-hidden rounded-md border border-hairline bg-surface shadow-lg"
          >
            <Command
              filter={(itemValue, search) =>
                itemValue.toLowerCase().includes(search.toLowerCase()) ? 1 : 0
              }
            >
              <div className="flex items-center gap-2 border-b border-hairline px-3">
                <MapPin aria-hidden className="size-3.5 shrink-0 text-ink-muted" />
                <Command.Input
                  autoFocus
                  placeholder={`Search ${options.length} areas…`}
                  className="h-9 flex-1 bg-transparent text-sm outline-none placeholder:text-ink-muted"
                />
              </div>

              {atCap && (
                <p className="border-b border-hairline px-3 py-1.5 text-xs text-ink-muted">
                  Showing the most you can compare at once ({max}). Remove one to add another.
                </p>
              )}

              <Command.List className="max-h-72 overflow-y-auto p-1">
                <Command.Empty className="px-3 py-6 text-center text-sm text-ink-muted">
                  No area matches that.
                </Command.Empty>
                {options.map((option) => {
                  const selected = value.includes(option.geo_code);
                  return (
                    <Command.Item
                      key={option.geo_code}
                      value={`${option.geo_name} ${option.geo_code}`}
                      onSelect={() => toggle(option.geo_code)}
                      // A greyed, unselectable row is more legible than hiding
                      // options once the cap is hit.
                      disabled={atCap && !selected}
                      className={cn(
                        "flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm",
                        "data-[selected=true]:bg-wash",
                        "data-[disabled=true]:cursor-not-allowed data-[disabled=true]:opacity-40",
                      )}
                    >
                      <Check
                        aria-hidden
                        className={cn("size-3.5 shrink-0", !selected && "opacity-0")}
                      />
                      <span className="truncate">{option.geo_name}</span>
                    </Command.Item>
                  );
                })}
              </Command.List>
            </Command>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>

      {value.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {value.map((code) => (
            <li key={code}>
              <button
                type="button"
                onClick={() => toggle(code)}
                aria-label={`Remove ${nameOf(code)}`}
                className={cn(
                  "flex items-center gap-1 rounded-full border border-hairline bg-wash/60 py-0.5 pl-2.5 pr-1.5 text-xs",
                  "hover:bg-wash focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent",
                )}
              >
                <span className="max-w-[12rem] truncate">{nameOf(code)}</span>
                <X aria-hidden className="size-3 shrink-0 text-ink-muted" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
