import type { components } from "./schema";
import { createEventParser, type ChatEvent } from "./events";

export type Category = components["schemas"]["Category"];
export type CategorySeries = components["schemas"]["CategorySeries"];
export type SeriesPoint = components["schemas"]["SeriesPoint"];
export type SubcategoryRef = components["schemas"]["SubcategoryRef"];
export type ApiError = components["schemas"]["ErrorResponse"];

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

export function fetchCategories(signal?: AbortSignal): Promise<Category[]> {
  return getJson<Category[]>("/api/datasets/census/categories", signal);
}

export function fetchSubcategories(signal?: AbortSignal): Promise<SubcategoryRef[]> {
  return getJson<SubcategoryRef[]>("/api/datasets/census/subcategories", signal);
}

export function fetchSeries(category: string, signal?: AbortSignal): Promise<CategorySeries> {
  return getJson<CategorySeries>(
    `/api/datasets/census/series?category=${encodeURIComponent(category)}`,
    signal,
  );
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
