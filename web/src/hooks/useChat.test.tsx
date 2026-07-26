import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatEvent } from "@/api/events";
import type { ChatTurn } from "@/api/client";

const streamChat = vi.fn();

vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return { ...actual, streamChat: (...args: unknown[]) => streamChat(...args) };
});

const { useChat } = await import("./useChat");
const { RequestFailed } = await import("@/api/client");

function emits(events: ChatEvent[]) {
  return async function* () {
    for (const event of events) yield event;
  };
}

function rejects(error: unknown) {
  // eslint-disable-next-line require-yield
  return async function* (): AsyncGenerator<ChatEvent> {
    throw error;
  };
}

beforeEach(() => streamChat.mockReset());

describe("useChat", () => {
  it("appends the question and the streamed answer", async () => {
    streamChat.mockImplementation(
      emits([
        { type: "text", text: "Boroondara had " },
        { type: "text", text: "167,900 people." },
        { type: "done", stop_reason: "end_turn" },
      ]),
    );

    const { result } = renderHook(() => useChat());
    act(() => result.current.send("How many people?"));

    await waitFor(() => expect(result.current.busy).toBe(false));

    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[0]).toEqual({
      role: "user",
      content: "How many people?",
    });
    const answer = result.current.messages[1];
    expect(answer.role === "assistant" && answer.text).toBe(
      "Boroondara had 167,900 people.",
    );
  });

  it("pairs each tool result with the call that produced it", async () => {
    streamChat.mockImplementation(
      emits([
        { type: "tool_use", id: "t1", name: "query_census", input: { category: "age" } },
        { type: "tool_use", id: "t2", name: "calculate_change", input: {} },
        { type: "tool_result", tool_use_id: "t2", content: "+5%", is_error: false },
        { type: "tool_result", tool_use_id: "t1", content: "[(2021, 1)]", is_error: false },
        { type: "done", stop_reason: "end_turn" },
      ]),
    );

    const { result } = renderHook(() => useChat());
    act(() => result.current.send("?"));
    await waitFor(() => expect(result.current.busy).toBe(false));

    const answer = result.current.messages[1];
    if (answer.role !== "assistant") throw new Error("expected an assistant turn");
    // Results arrive out of order relative to the calls, so matching by id
    // rather than by position is what keeps the chips truthful.
    expect(answer.steps.map((s) => [s.id, s.result?.content])).toEqual([
      ["t1", "[(2021, 1)]"],
      ["t2", "+5%"],
    ]);
  });

  it("sends the whole conversation on a follow-up", async () => {
    streamChat.mockImplementation(emits([{ type: "text", text: "40,100." }]));
    const { result } = renderHook(() => useChat());

    act(() => result.current.send("How many separate houses in 2021?"));
    await waitFor(() => expect(result.current.busy).toBe(false));

    streamChat.mockImplementation(emits([{ type: "text", text: "39,500." }]));
    act(() => result.current.send("And in 2016?"));
    await waitFor(() => expect(result.current.busy).toBe(false));

    // The server is stateless, so a follow-up only works if the client resends
    // everything. This is the bug the old single-shot ask() had.
    const history = streamChat.mock.calls[1][0] as ChatTurn[];
    expect(history).toEqual([
      { role: "user", content: "How many separate houses in 2021?" },
      { role: "assistant", content: "40,100." },
      { role: "user", content: "And in 2016?" },
    ]);
  });

  it("keeps partial text when an error arrives mid-stream", async () => {
    streamChat.mockImplementation(
      emits([
        { type: "text", text: "Partial answer" },
        { type: "error", message: "upstream failed", retryable: true },
      ]),
    );

    const { result } = renderHook(() => useChat());
    act(() => result.current.send("?"));
    await waitFor(() => expect(result.current.busy).toBe(false));

    const answer = result.current.messages[1];
    if (answer.role !== "assistant") throw new Error("expected an assistant turn");
    expect(answer.text).toBe("Partial answer");
    expect(answer.error).toEqual({ message: "upstream failed", retryable: true });
  });

  it("enters a cooldown on 429 and drops the empty answer bubble", async () => {
    streamChat.mockImplementation(
      rejects(
        new RequestFailed(429, {
          detail: "Too many requests.",
          kind: "rate",
          retry_after: 3,
        }),
      ),
    );

    const { result } = renderHook(() => useChat());
    act(() => result.current.send("?"));

    await waitFor(() => expect(result.current.cooldown).not.toBeNull());
    expect(result.current.cooldown?.secondsLeft).toBe(3);
    expect(result.current.cooldown?.kind).toBe("rate");
    // Rejected before the stream opened, so there is no partial answer — a
    // blank assistant bubble would just look broken.
    expect(result.current.messages.map((m) => m.role)).toEqual(["user"]);
  });

  it("refuses to send while cooling down", async () => {
    streamChat.mockImplementation(
      rejects(
        new RequestFailed(429, { detail: "Slow down.", kind: "rate", retry_after: 5 }),
      ),
    );

    const { result } = renderHook(() => useChat());
    act(() => result.current.send("first"));
    await waitFor(() => expect(result.current.cooldown).not.toBeNull());

    streamChat.mockClear();
    act(() => result.current.send("second"));
    expect(streamChat).not.toHaveBeenCalled();
  });

  it("distinguishes a capacity rejection from a rate one", async () => {
    streamChat.mockImplementation(
      rejects(
        new RequestFailed(429, {
          detail: "The assistant is busy right now.",
          kind: "capacity",
          retry_after: 10,
        }),
      ),
    );

    const { result } = renderHook(() => useChat());
    act(() => result.current.send("?"));

    // Different copy in the UI: capacity is not the caller's fault.
    await waitFor(() => expect(result.current.cooldown?.kind).toBe("capacity"));
  });

  it("ignores an empty question", () => {
    const { result } = renderHook(() => useChat());
    act(() => result.current.send("   "));
    expect(streamChat).not.toHaveBeenCalled();
    expect(result.current.messages).toEqual([]);
  });

  it("surfaces a transport failure as a retryable error", async () => {
    streamChat.mockImplementation(rejects(new TypeError("network down")));

    const { result } = renderHook(() => useChat());
    act(() => result.current.send("?"));
    await waitFor(() => expect(result.current.busy).toBe(false));

    const answer = result.current.messages[1];
    expect(answer.role === "assistant" && answer.error?.retryable).toBe(true);
  });
});
