import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatPane } from "./ChatPane";
import type { AssistantMessage, Message } from "@/hooks/useChat";

function answer(text: string): AssistantMessage {
  return { role: "assistant", text, steps: [], streaming: false };
}

function paneWith(messages: Message[]) {
  return render(
    <ChatPane
      messages={messages}
      busy={false}
      cooldown={null}
      onSend={vi.fn()}
      onRetry={vi.fn()}
      onStop={vi.fn()}
      onCite={vi.fn()}
    />,
  );
}

// Verbatim from a real answer. The model reaches for a table whenever it is
// asked for a breakdown, so this is the common case, not an edge one.
const TABLE_ANSWER = `Here's the breakdown of dwelling types in Boroondara in 2021:

| Dwelling Type | Number | Percentage |
|---------------|--------|------------|
| Separate house | 35,498 | 55.0% |
| Flat or apartment | 15,959 | 24.7% |
| Semi-detached, row or terrace house | 12,881 | 20.0% |
| Other dwelling | 251 | 0.4% |
| Dwelling structure not stated | 86 | 0.1% |
| Total | 64,675 | 100% |

Key insights:

* Separate houses remain the dominant dwelling type, representing over half
* Apartments/flats make up nearly a quarter of housing stock`;

describe("ChatPane markdown rendering", () => {
  it("renders a GFM table as a real table", () => {
    // Regression: tables are a GFM extension, not core Markdown. Without
    // remark-gfm this parsed as one paragraph and HTML collapsed the row
    // newlines into spaces, so the whole table rendered as a single run-on
    // line. Styling it in CSS was not enough — the plugin has to be enabled.
    paneWith([{ role: "user", content: "breakdown?" }, answer(TABLE_ANSWER)]);

    const table = screen.getByRole("table");
    expect(table).toBeTruthy();

    expect(screen.getByRole("columnheader", { name: "Dwelling Type" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Number" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Percentage" })).toBeTruthy();

    // Five dwelling types plus the total row.
    expect(table.querySelectorAll("tbody tr")).toHaveLength(6);

    const cells = [...table.querySelectorAll("tbody tr")].map((row) =>
      [...row.querySelectorAll("td")].map((c) => c.textContent),
    );
    expect(cells[0]).toEqual(["Separate house", "35,498", "55.0%"]);
    expect(cells[5]).toEqual(["Total", "64,675", "100%"]);
  });

  it("does not flatten the table into a paragraph", () => {
    const { container } = paneWith([answer(TABLE_ANSWER)]);

    // The precise failure mode: a paragraph containing the pipe-delimited rows
    // run together. Asserting the table exists is not enough — a fallback
    // paragraph could coexist with it.
    const paragraphs = [...container.querySelectorAll("p")].map((p) => p.textContent ?? "");
    expect(paragraphs.some((text) => text.includes("|---"))).toBe(false);
    expect(paragraphs.some((text) => /\|.*\|.*\|/.test(text))).toBe(false);
  });

  it("still renders lists and prose around the table", () => {
    const { container } = paneWith([answer(TABLE_ANSWER)]);

    expect(container.querySelectorAll("ul li")).toHaveLength(2);
    expect(screen.getByText(/breakdown of dwelling types/)).toBeTruthy();
  });

  it("keeps the table inside a horizontally scrollable container", () => {
    const { container } = paneWith([answer(TABLE_ANSWER)]);

    // A breakdown table is wider than the chat pane; it must scroll itself
    // rather than pushing the page sideways.
    const wrapper = container.querySelector("table")?.parentElement;
    expect(wrapper?.className).toContain("overflow-x-auto");
  });

  it("keeps min-w-0 on the pane so wide content cannot widen the page", () => {
    const { container } = paneWith([answer(TABLE_ANSWER)]);

    // jsdom does no layout, so this guards the class rather than the effect.
    // Without min-w-0 the pane is a grid item with min-width:auto, refuses to
    // shrink below its content, and a wide table pushes the whole page
    // sideways instead of scrolling in its own container. Verified for real in
    // a browser; this exists so removing the class does not pass silently.
    const section = container.querySelector("section");
    expect(section?.className).toContain("min-w-0");
  });

  it("renders an ordinary answer with no table", () => {
    const { container } = paneWith([answer("The population in 2021 was **167,900**.")]);

    expect(container.querySelector("table")).toBeNull();
    expect(container.querySelector("strong")?.textContent).toBe("167,900");
  });
});
