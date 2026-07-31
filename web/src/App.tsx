import { useState } from "react";
import { ChatPane } from "./components/ChatPane";
import { ExplorerPane, type Selection } from "./components/ExplorerPane";
import { useChat } from "./hooks/useChat";

const DEFAULT_LEVEL = "LGA";

export default function App() {
  const { messages, send, retry, stop, busy, cooldown } = useChat();
  const [level, setLevel] = useState<string>(DEFAULT_LEVEL);
  const [geoCodes, setGeoCodes] = useState<string[]>([]);
  const [selection, setSelection] = useState<Selection | null>(null);

  return (
    <div className="mx-auto flex min-h-[100dvh] max-w-[1600px] flex-col gap-4 p-4 lg:h-[100dvh]">
      <header>
        <h1 className="text-base font-semibold">Australian Census Explorer</h1>
        <p className="text-xs text-ink-secondary">
          ABS Census Time Series — compare local areas or states across 2011, 2016 and 2021
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
          // A chat citation carries the whole context — level, areas and the
          // metric — so following it reproduces exactly what the agent queried.
          onCite={(citation) => {
            setLevel(citation.level);
            setGeoCodes(citation.geoCodes);
            setSelection({ category: citation.category, subcategory: citation.subcategory });
          }}
        />
        <ExplorerPane
          level={level}
          geoCodes={geoCodes}
          selection={selection}
          onLevelChange={setLevel}
          onGeoCodesChange={setGeoCodes}
          onSelect={setSelection}
        />
      </main>
    </div>
  );
}
