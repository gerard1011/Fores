/**
 * SSE event types and frame parser.
 *
 * These types are hand-written and mirror the docstring on
 * `agent.stream_ask` in the Python backend. OpenAPI cannot describe an SSE
 * body, so unlike everything in schema.d.ts there is no generator keeping
 * these two in sync — if you change an event shape, change it in both places.
 */

export type ChatEvent =
  | { type: "text"; text: string }
  | { type: "tool_use"; id: string; name: string; input: Record<string, unknown> }
  | { type: "tool_result"; tool_use_id: string; content: string; is_error: boolean }
  | { type: "error"; message: string; retryable: boolean }
  | { type: "done"; stop_reason: string };

/**
 * Incremental SSE frame parser.
 *
 * A network chunk has no relationship to a frame boundary: one chunk can carry
 * three frames, and a single frame can be split across two chunks mid-JSON.
 * Parsing each chunk independently works right up until it doesn't, so this
 * buffers and only emits on a complete `\n\n` terminator.
 */
export function createEventParser() {
  let buffer = "";

  return {
    /** Feed a chunk; get back whatever complete events it completed. */
    push(chunk: string): ChatEvent[] {
      buffer += chunk;
      const events: ChatEvent[] = [];

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);

        const payload = frame
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");

        if (payload) {
          try {
            events.push(JSON.parse(payload) as ChatEvent);
          } catch {
            // A malformed frame is not worth tearing the stream down for —
            // drop it and keep reading the rest.
          }
        }
        boundary = buffer.indexOf("\n\n");
      }

      return events;
    },

    /** Anything left after the stream closed — a truncated final frame. */
    remainder(): string {
      return buffer;
    },
  };
}
