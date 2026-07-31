import { describe, expect, it } from "vitest";
import type { CategorySeries } from "@/api/client";
import { toAreaRows, toRows } from "./SeriesChart";

function series(points: CategorySeries["points"], geographies: CategorySeries["geographies"]): CategorySeries {
  return {
    category: "population",
    level: "STE",
    geographies,
    years: [2011, 2016, 2021],
    points,
  };
}

describe("toRows (single-area view)", () => {
  it("pivots points into one row per subcategory keyed by year", () => {
    const rows = toRows(
      series(
        [
          { geo_code: "2", geo_name: "Victoria", subcategory: "total", year: 2011, value: 100 },
          { geo_code: "2", geo_name: "Victoria", subcategory: "total", year: 2021, value: 130 },
          { geo_code: "2", geo_name: "Victoria", subcategory: "male", year: 2011, value: 49 },
        ],
        [{ geo_code: "2", geo_name: "Victoria" }],
      ),
    );

    const total = rows.find((r) => r.label === "total");
    expect(total).toMatchObject({ label: "total", 2011: 100, 2021: 130 });
    expect(rows.map((r) => r.label).sort()).toEqual(["male", "total"]);
  });
});

describe("toAreaRows (comparison view)", () => {
  const s = series(
    [
      { geo_code: "1", geo_name: "New South Wales", subcategory: "total", year: 2011, value: 700 },
      { geo_code: "1", geo_name: "New South Wales", subcategory: "total", year: 2021, value: 800 },
      { geo_code: "2", geo_name: "Victoria", subcategory: "total", year: 2011, value: 500 },
      // A subcategory we are not focusing on must be filtered out.
      { geo_code: "2", geo_name: "Victoria", subcategory: "male", year: 2011, value: 245 },
    ],
    [
      { geo_code: "1", geo_name: "New South Wales" },
      { geo_code: "2", geo_name: "Victoria" },
      { geo_code: "4", geo_name: "South Australia" },
    ],
  );

  it("makes one row per area for the focused subcategory", () => {
    const rows = toAreaRows(s, "total");
    const nsw = rows.find((r) => r.label === "New South Wales");
    expect(nsw).toMatchObject({ 2011: 700, 2021: 800 });
    const vic = rows.find((r) => r.label === "Victoria");
    // The "male" point must not leak into the "total" comparison.
    expect(vic).toMatchObject({ 2011: 500 });
    expect(vic!["male" as unknown as number]).toBeUndefined();
  });

  it("seeds every requested area so a gap shows as a row, not a disappearance", () => {
    const rows = toAreaRows(s, "total");
    const sa = rows.find((r) => r.label === "South Australia");
    // South Australia had no rows for the subcategory but must still appear.
    expect(sa).toBeDefined();
    expect(sa![2011]).toBeUndefined();
  });
});
