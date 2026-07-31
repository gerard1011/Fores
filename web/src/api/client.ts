import type { components } from "./schema";
import { createEventParser, type ChatEvent } from "./events";

export type Category = components["schemas"]["Category"];
export type CategorySeries = components["schemas"]["CategorySeries"];
export type SeriesPoint = components["schemas"]["SeriesPoint"];
export type SubcategoryRef = components["schemas"]["SubcategoryRef"];
export type Level = components["schemas"]["Level"];
export type Geography = components["schemas"]["Geography"];
export type ApiError = components["schemas"]["ErrorResponse"];

const CENSUS = "/api/datasets/census";

/** A non-2xx response, carrying the server's structured error body. */
export class RequestFailed extends Error {
  constructor(
    readonly status: number,
    readonly body: ApiError,
  ) {
    super(body.detail);
    this.name = "RequestFailed";
  }

  get kind() {
    return this.body.kind;
  }

  /** Seconds to wait, from the body or the Retry-After header. */
  get retryAfter(): number {
    return this.body.retry_after ?? 5;
  }
}

async function failure(response: Response): Promise<RequestFailed> {
  let body: ApiError;
  try {
    body = (await response.json()) as ApiError;
  } catch {
    // A proxy error or a crash before the handler will not be our JSON shape.
    body = { detail: `Request failed (${response.status}).`, kind: "unavailable" };
  }
  const header = response.headers.get("Retry-After");
  if (header && body.retry_after == null) body.retry_after = Number(header);
  return new RequestFailed(response.status, body);
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw await failure(response);
  return (await response.json()) as T;
}

export function fetchLevels(signal?: AbortSignal): Promise<Level[]> {
  return getJson<Level[]>(`${CENSUS}/levels`, signal);
}

export function fetchGeographies(level: string, signal?: AbortSignal): Promise<Geography[]> {
  return getJson<Geography[]>(`${CENSUS}/geographies?level=${encodeURIComponent(level)}`, signal);
}

export function fetchCategories(level: string, signal?: AbortSignal): Promise<Category[]> {
  return getJson<Category[]>(`${CENSUS}/categories?level=${encodeURIComponent(level)}`, signal);
}

export function fetchSubcategories(level: string, signal?: AbortSignal): Promise<SubcategoryRef[]> {
  return getJson<SubcategoryRef[]>(
    `${CENSUS}/subcategories?level=${encodeURIComponent(level)}`,
    signal,
  );
}

/** Compare one category across N areas. `geo` repeats, one per area. */
export function fetchSeries(
  category: string,
  level: string,
  geoCodes: string[],
  signal?: AbortSignal,
): Promise<CategorySeries> {
  const params = new URLSearchParams({ category, level });
  for (const code of geoCodes) params.append("geo", code);
  return getJson<CategorySeries>(`${CENSUS}/series?${params.toString()}`, signal);
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

/**
 * POST the conversation and yield events as they arrive.
 *
 * Rejections happen before the stream opens and surface as RequestFailed, not
 * as an `error` event — the caller needs a status code it can branch on before
 * it starts rendering a message.
 */
export async function* streamChat(
  messages: ChatTurn[],
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
    signal,
  });

  if (!response.ok) throw await failure(response);
  if (!response.body) throw new Error("The server returned no response body.");

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const parser = createEventParser();

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      for (const event of parser.push(value)) yield event;
    }
  } finally {
    // Releasing the lock lets the underlying connection tear down promptly when
    // the caller aborts, which is what frees the server's concurrency slot.
    reader.releaseLock();
  }
}
