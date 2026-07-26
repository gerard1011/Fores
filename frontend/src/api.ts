const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface LookupResult {
  year: number;
  value: number;
}

async function handle<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`Request failed (${response.status}): ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

export function askQuestion(question: string): Promise<string> {
  return fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  })
    .then((res) => handle<{ answer: string }>(res))
    .then((data) => data.answer);
}

export function getCategories(): Promise<string[]> {
  return fetch(`${API_BASE_URL}/categories`).then((res) => handle<string[]>(res));
}

export function getSubcategories(category: string): Promise<string[]> {
  const params = new URLSearchParams({ category });
  return fetch(`${API_BASE_URL}/subcategories?${params}`).then((res) => handle<string[]>(res));
}

export function lookupCensusData(category: string, subcategory: string): Promise<LookupResult[]> {
  const params = new URLSearchParams({ category, subcategory });
  return fetch(`${API_BASE_URL}/lookup?${params}`).then((res) => handle<LookupResult[]>(res));
}
