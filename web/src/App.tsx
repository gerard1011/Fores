import { useState } from "react";
import { ChatPane } from "./components/ChatPane";
import { ExplorerPane, type Selection } from "./components/ExplorerPane";
import { useChat } from "./hooks/useChat";

export default function App() {
  const { messages, send, retry, stop, busy, cooldown } = useChat();
  const [selection, setSelection] = useState<Selection | null>(null);

  return (
    <div className="mx-auto flex min-h-[100dvh] max-w-[1600px] flex-col gap-4 p-4 lg:h-[100dvh]">
      <header>
        <h1 className="text-base font-semibold">Boroondara Census Assistant</h1>
        <p className="text-xs text-ink-secondary">
          ABS Census Time Series — 2011, 2016 and 2021
        </p>
      </header>

      {/*
        Two panes side by side on wide screens so an answer and the data it
        cites are visible at once — that pairing is the point, and it is what
        the stacked Streamlit layout could not do. Below lg they stack, chat
        first, and each pane scrolls its own body.
      */}
      <main className="grid flex-1 gap-4 lg:min-h-0 lg:grid-cols-2">
        <ChatPane
          messages={messages}
          busy={busy}
          cooldown={cooldown}
          onSend={send}
          onRetry={retry}
          onStop={stop}
          onCite={(citation) => setSelection(citation)}
        />
        <ExplorerPane selection={selection} onSelect={setSelection} />
      </main>
    </div>
  );
}
