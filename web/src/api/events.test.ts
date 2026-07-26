import { describe, expect, it } from "vitest";
import { createEventParser, type ChatEvent } from "./events";

function frame(event: ChatEvent): string {
  return `data: ${JSON.stringify(event)}\n\n`;
}

describe("createEventParser", () => {
  it("parses a single complete frame", () => {
    const parser = createEventParser();
    expect(parser.push(frame({ type: "text", text: "hello" }))).toEqual([
      { type: "text", text: "hello" },
    ]);
  });

  it("parses several frames arriving in one chunk", () => {
    const parser = createEventParser();
    const chunk =
      frame({ type: "text", text: "a" }) +
      frame({ type: "text", text: "b" }) +
      frame({ type: "done", stop_reason: "end_turn" });

    expect(parser.push(chunk).map((e) => e.type)).toEqual(["text", "text", "done"]);
  });

  it("holds back a frame split across chunks", () => {
    const parser = createEventParser();
    const whole = frame({ type: "text", text: "split me" });
    const cut = Math.floor(whole.length / 2);

    // A network chunk boundary lands wherever it lands — usually mid-JSON.
    // Emitting on the first half would produce a parse error and a lost token.
    expect(parser.push(whole.slice(0, cut))).toEqual([]);
    expect(parser.push(whole.slice(cut))).toEqual([{ type: "text", text: "split me" }]);
  });

  it("reassembles a frame split at every possible offset", () => {
    const whole = frame({ type: "text", text: "boundary torture" });

    for (let cut = 1; cut < whole.length; cut++) {
      const parser = createEventParser();
      const events = [
        ...parser.push(whole.slice(0, cut)),
        ...parser.push(whole.slice(cut)),
      ];
      expect(events, `split at ${cut}`).toEqual([
        { type: "text", text: "boundary torture" },
      ]);
    }
  });

  it("emits completed frames and keeps the trailing partial", () => {
    const parser = createEventParser();
    const chunk = frame({ type: "text", text: "done" }) + 'data: {"type":"te';

    expect(parser.push(chunk)).toEqual([{ type: "text", text: "done" }]);
    expect(parser.remainder()).toBe('data: {"type":"te');
  });

  it("preserves structured tool payloads", () => {
    const parser = createEventParser();
    const event: ChatEvent = {
      type: "tool_use",
      id: "toolu_1",
      name: "query_census",
      input: { category: "dwelling_structure", subcategory: "separate house" },
    };

    // The explorer link reads straight off this object, so it has to survive
    // the wire unflattened.
    expect(parser.push(frame(event))).toEqual([event]);
  });

  it("survives text containing a frame terminator", () => {
    const parser = createEventParser();
    const event: ChatEvent = { type: "text", text: "line one\n\nline two" };

    // JSON escapes the newlines, so the literal \n\n never reaches the buffer
    // as a separator — worth pinning, since it would truncate an answer.
    expect(parser.push(frame(event))).toEqual([event]);
  });

  it("skips a malformed frame without dropping the rest", () => {
    const parser = createEventParser();
    const chunk = "data: {not json}\n\n" + frame({ type: "done", stop_reason: "end_turn" });

    expect(parser.push(chunk)).toEqual([{ type: "done", stop_reason: "end_turn" }]);
  });

  it("accepts data lines with no space after the colon", () => {
    const parser = createEventParser();
    expect(parser.push('data:{"type":"text","text":"tight"}\n\n')).toEqual([
      { type: "text", text: "tight" },
    ]);
  });

  it("ignores comment and non-data lines", () => {
    const parser = createEventParser();
    const chunk = ": keep-alive\n\n" + frame({ type: "text", text: "real" });

    expect(parser.push(chunk)).toEqual([{ type: "text", text: "real" }]);
  });

  it("returns nothing for an empty chunk", () => {
    const parser = createEventParser();
    expect(parser.push("")).toEqual([]);
  });
});
