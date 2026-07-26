import { useCallback, useEffect, useRef, useState } from "react";
import { RequestFailed, streamChat, type ChatTurn } from "@/api/client";

export interface ToolStep {
  id: string;
  name: string;
  input: Record<string, unknown>;
  result?: { content: string; isError: boolean };
}

export interface UserMessage {
  role: "user";
  content: string;
}

export interface AssistantMessage {
  role: "assistant";
  text: string;
  steps: ToolStep[];
  error?: { message: string; retryable: boolean };
  streaming: boolean;
}

export type Message = UserMessage | AssistantMessage;

/** Set while the server has told us to back off, so the composer can lock. */
export interface Cooldown {
  secondsLeft: number;
  reason: string;
  /** "rate" is the caller's own doing; "capacity" is the server being busy. */
  kind: string;
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [cooldown, setCooldown] = useState<Cooldown | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const busy = messages.some((m) => m.role === "assistant" && m.streaming);

  // Tick the cooldown down so the composer can show a countdown rather than an
  // unexplained disabled state.
  useEffect(() => {
    if (!cooldown) return;
    if (cooldown.secondsLeft <= 0) {
      setCooldown(null);
      return;
    }
    const timer = setTimeout(
      () => setCooldown((c) => (c ? { ...c, secondsLeft: c.secondsLeft - 1 } : null)),
      1000,
    );
    return () => clearTimeout(timer);
  }, [cooldown]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const patchLast = useCallback((patch: (m: AssistantMessage) => AssistantMessage) => {
    setMessages((current) => {
      const next = [...current];
      const last = next[next.length - 1];
      if (last?.role !== "assistant") return current;
      next[next.length - 1] = patch(last);
      return next;
    });
  }, []);

  const run = useCallback(
    async (history: ChatTurn[]) => {
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        for await (const event of streamChat(history, controller.signal)) {
          switch (event.type) {
            case "text":
              patchLast((m) => ({ ...m, text: m.text + event.text }));
              break;
            case "tool_use":
              patchLast((m) => ({
                ...m,
                steps: [
                  ...m.steps,
                  { id: event.id, name: event.name, input: event.input },
                ],
              }));
              break;
            case "tool_result":
              patchLast((m) => ({
                ...m,
                steps: m.steps.map((s) =>
                  s.id === event.tool_use_id
                    ? { ...s, result: { content: event.content, isError: event.is_error } }
                    : s,
                ),
              }));
              break;
            case "error":
              patchLast((m) => ({
                ...m,
                error: { message: event.message, retryable: event.retryable },
              }));
              break;
            case "done":
              break;
          }
        }
        patchLast((m) => ({ ...m, streaming: false }));
      } catch (err) {
        if (controller.signal.aborted) {
          // Deliberate stop: keep whatever streamed, just mark it finished.
          patchLast((m) => ({ ...m, streaming: false }));
          return;
        }
        if (err instanceof RequestFailed && err.status === 429) {
          // Rejected before the stream opened, so there is no partial answer.
          // Drop the empty assistant turn rather than leaving a blank bubble.
          setMessages((current) => current.slice(0, -1));
          setCooldown({
            secondsLeft: err.retryAfter,
            reason: err.body.detail,
            kind: err.kind,
          });
          return;
        }
        const message =
          err instanceof RequestFailed ? err.body.detail : "Could not reach the server.";
        patchLast((m) => ({ ...m, streaming: false, error: { message, retryable: true } }));
      } finally {
        abortRef.current = null;
      }
    },
    [patchLast],
  );

  const send = useCallback(
    (question: string) => {
      const text = question.trim();
      if (!text || busy || cooldown) return;

      // The server is stateless, so the client owns the history and sends it
      // whole. Only finished text turns go back — the server rebuilds tool
      // blocks itself within a request.
      const history: ChatTurn[] = [
        ...messages
          .filter((m): m is Message => m.role === "user" || !!m.text)
          .map<ChatTurn>((m) =>
            m.role === "user"
              ? { role: "user", content: m.content }
              : { role: "assistant", content: m.text },
          ),
        { role: "user", content: text },
      ];

      setMessages((current) => [
        ...current,
        { role: "user", content: text },
        { role: "assistant", text: "", steps: [], streaming: true },
      ]);

      void run(history);
    },
    [busy, cooldown, messages, run],
  );

  const retry = useCallback(() => {
    // The failed exchange is the last user turn plus its empty answer; replay
    // the question rather than making the user retype it.
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser || lastUser.role !== "user" || busy) return;

    setMessages((current) => current.slice(0, -1));
    const history: ChatTurn[] = messages
      .slice(0, -1)
      .filter((m) => m.role === "user" || !!m.text)
      .map<ChatTurn>((m) =>
        m.role === "user"
          ? { role: "user", content: m.content }
          : { role: "assistant", content: m.text },
      );

    setMessages((current) => [
      ...current,
      { role: "assistant", text: "", steps: [], streaming: true },
    ]);
    void run(history);
  }, [busy, messages, run]);

  const stop = useCallback(() => abortRef.current?.abort(), []);

  return { messages, send, retry, stop, busy, cooldown };
}
