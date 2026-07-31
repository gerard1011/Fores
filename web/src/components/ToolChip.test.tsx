import { describe, expect, it } from "vitest";
import type { ToolStep } from "@/hooks/useChat";
import { citationOf } from "./ToolChip";

function step(name: string, input: Record<string, unknown>): ToolStep {
  return { id: "toolu_1", name, input };
}

describe("citationOf", () => {
  it("reads level and geo_codes off a query_census step", () => {
    const citation = citationOf(
      step("query_census", {
        category: "population",
        subcategory: "total",
        level: "STE",
        geo_codes: ["1", "2"],
      }),
    );
    expect(citation).toEqual({
      category: "population",
      subcategory: "total",
      level: "STE",
      geoCodes: ["1", "2"],
    });
  });

  it("is not a citation for other tools", () => {
    expect(citationOf(step("find_geography", { level: "LGA", name_query: "Boroondara" }))).toBeNull();
    expect(citationOf(step("calculate_change", { value_start: 1, value_end: 2 }))).toBeNull();
  });

  it("rejects a malformed query_census input rather than half-driving the explorer", () => {
    // Missing geo_codes, or a non-string in it — following this would set an
    // area selection the picker cannot honour.
    expect(citationOf(step("query_census", { category: "population", subcategory: "total", level: "STE" }))).toBeNull();
    expect(
      citationOf(
        step("query_census", {
          category: "population",
          subcategory: "total",
          level: "STE",
          geo_codes: ["1", 2],
        }),
      ),
    ).toBeNull();
  });
});
