import { useState, useEffect } from "react";
import { getCategories, getSubcategories, lookupCensusData, type LookupResult } from "./api";

export default function LookupPanel() {
  const [categories, setCategories] = useState<string[]>([]);
  const [subcategories, setSubcategories] = useState<string[]>([]);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [selectedSubcategory, setSelectedSubcategory] = useState("");
  const [results, setResults] = useState<LookupResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCategories()
      .then((cats) => {
        setCategories(cats);
        if (cats.length > 0) setSelectedCategory(cats[0]);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load categories."));
  }, []);

  useEffect(() => {
    if (!selectedCategory) return;
    setResults(null);
    getSubcategories(selectedCategory)
      .then((subs) => {
        setSubcategories(subs);
        setSelectedSubcategory(subs[0] ?? "");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load subcategories."));
  }, [selectedCategory]);

  async function handleLookup() {
    if (!selectedCategory || !selectedSubcategory) return;
    setLoading(true);
    setError(null);
    try {
      const data = await lookupCensusData(selectedCategory, selectedSubcategory);
      setResults(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lookup failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <h2 className="mb-1 text-lg font-semibold text-gray-900">Manual lookup</h2>
      <p className="mb-3 text-sm text-gray-500">Verify the AI's answers directly against the data.</p>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <label className="flex-1 text-sm text-gray-700">
          Category
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="mt-1 w-full rounded-md border border-gray-300 px-2 py-2 text-sm focus:border-blue-500 focus:outline-none"
          >
            {categories.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
        </label>

        <label className="flex-1 text-sm text-gray-700">
          Subcategory
          <select
            value={selectedSubcategory}
            onChange={(e) => setSelectedSubcategory(e.target.value)}
            className="mt-1 w-full rounded-md border border-gray-300 px-2 py-2 text-sm focus:border-blue-500 focus:outline-none"
          >
            {subcategories.map((subcategory) => (
              <option key={subcategory} value={subcategory}>
                {subcategory}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          onClick={handleLookup}
          disabled={loading || !selectedCategory || !selectedSubcategory}
          className="rounded-md bg-gray-800 px-4 py-2 text-sm font-medium text-white hover:bg-gray-900 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Look up
        </button>
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      {results && (
        <div className="mt-4">
          <p className="mb-2 text-sm font-medium text-gray-700">
            Results for {selectedCategory} — {selectedSubcategory}:
          </p>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-gray-500">
                <th className="py-1 pr-4 font-medium">Year</th>
                <th className="py-1 font-medium">Value</th>
              </tr>
            </thead>
            <tbody>
              {results.map(({ year, value }) => (
                <tr key={year} className="border-b border-gray-100">
                  <td className="py-1 pr-4 text-gray-800">{year}</td>
                  <td className="py-1 text-gray-800">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
