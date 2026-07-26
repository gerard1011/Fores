import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import { AlertCircle, ArrowUp, Clock, Square } from "lucide-react";
import type { AssistantMessage, Cooldown, Message } from "@/hooks/useChat";
import { ToolChip, type Citation } from "./ToolChip";
import { cn } from "@/lib/utils";

interface Props {
  messages: Message[];
  busy: boolean;
  cooldown: Cooldown | null;
  onSend: (question: string) => void;
  onRetry: () => void;
  onStop: () => void;
  onCite: (citation: Citation) => void;
}

const EXAMPLES = [
  "How did the number of separate houses change between 2016 and 2021?",
  "What's the breakdown of dwelling types in 2021?",
  "How many people were aged 20-24 in 2016?",
];

export function ChatPane({
  messages,
  busy,
  cooldown,
  onSend,
  onRetry,
  onStop,
  onCite,
}: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  return (
    <section
      aria-label="Ask a question"
      className="flex min-h-[26rem] flex-col rounded-lg border border-hairline bg-surface lg:min-h-0"
    >
      <header className="border-b border-hairline px-4 py-3">
        <h2 className="text-sm font-semibold">Ask</h2>
        <p className="text-xs text-ink-secondary">
          Answers cite the data they used — expand a step to check it.
        </p>
      </header>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <Empty onPick={onSend} disabled={busy || !!cooldown} />
        ) : (
          messages.map((message, i) =>
            message.role === "user" ? (
              <UserBubble key={i} text={message.content} />
            ) : (
              <AssistantBubble
                key={i}
                message={message}
                onCite={onCite}
                onRetry={onRetry}
              />
            ),
          )
        )}
        <div ref={endRef} />
      </div>

      <Composer
        busy={busy}
        cooldown={cooldown}
        onSend={onSend}
        onStop={onStop}
      />
    </section>
  );
}

function Empty({ onPick, disabled }: { onPick: (q: string) => void; disabled: boolean }) {
  return (
    <div className="py-6">
      <p className="mb-3 text-sm text-ink-secondary">
        Ask about Boroondara census data from 2011, 2016 and 2021.
      </p>
      <ul className="space-y-1.5">
        {EXAMPLES.map((example) => (
          <li key={example}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onPick(example)}
              className={cn(
                "w-full rounded-md border border-hairline px-3 py-2 text-left text-sm",
                "text-ink-secondary transition-colors hover:bg-wash disabled:opacity-50",
              )}
            >
              {example}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-lg rounded-br-sm bg-wash px-3 py-2 text-sm">
        {text}
      </div>
    </div>
  );
}

function AssistantBubble({
  message,
  onCite,
  onRetry,
}: {
  message: AssistantMessage;
  onCite: (citation: Citation) => void;
  onRetry: () => void;
}) {
  const thinking = message.streaming && !message.text && message.steps.length === 0;

  return (
    <div className="space-y-2">
      {message.steps.length > 0 && (
        <div className="space-y-1">
          {message.steps.map((step) => (
            <ToolChip key={step.id} step={step} onSelect={onCite} />
          ))}
        </div>
      )}

      {thinking && (
        <p className="text-sm text-ink-muted" role="status">
          Thinking…
        </p>
      )}

      {message.text && (
        <div className="prose-answer text-sm">
          <Markdown>{message.text}</Markdown>
          {message.streaming && <span className="streaming-caret" aria-hidden />}
        </div>
      )}

      {message.error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-critical/40 bg-critical/5 px-3 py-2 text-sm"
        >
          <AlertCircle aria-hidden className="mt-0.5 size-4 shrink-0 text-critical" />
          <div className="min-w-0 flex-1">
            <p className="text-ink">{message.error.message}</p>
            {message.error.retryable && (
              <button
                type="button"
                onClick={onRetry}
                className="mt-1 text-xs font-medium text-accent underline underline-offset-2"
              >
                Retry
              </button>
            )}
          </div>
        </div>
      )}

      {/* Streaming stopped with nothing to show and no error is still a real
          outcome — say so rather than leaving an empty bubble. */}
      {!message.streaming && !message.text && !message.error && (
        <p className="text-sm text-ink-muted">No answer was returned.</p>
      )}
    </div>
  );
}

function Composer({
  busy,
  cooldown,
  onSend,
  onStop,
}: {
  busy: boolean;
  cooldown: Cooldown | null;
  onSend: (q: string) => void;
  onStop: () => void;
}) {
  const [value, setValue] = useState("");
  const locked = !!cooldown;

  function submit() {
    if (!value.trim() || busy || locked) return;
    onSend(value);
    setValue("");
  }

  return (
    <div className="border-t border-hairline p-3">
      {cooldown && (
        <div
          role="status"
          className="mb-2 flex items-center gap-2 rounded-md border border-hairline bg-wash px-3 py-2 text-xs text-ink-secondary"
        >
          <Clock aria-hidden className="size-3.5 shrink-0" />
          <span>
            {cooldown.reason}{" "}
            <span className="tabular-nums">
              {cooldown.secondsLeft}s
            </span>
          </span>
        </div>
      )}

      <div className="flex items-end gap-2">
        <textarea
          rows={1}
          value={value}
          disabled={locked}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={locked ? "Waiting…" : "Ask about Boroondara census data…"}
          aria-label="Your question"
          className={cn(
            "max-h-32 min-h-9 flex-1 resize-none rounded-md border border-hairline bg-page px-3 py-2 text-sm",
            "placeholder:text-ink-muted focus-visible:outline-2 focus-visible:outline-accent",
            "disabled:opacity-60",
          )}
        />
        {busy ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop generating"
            className="flex size-9 shrink-0 items-center justify-center rounded-md border border-hairline hover:bg-wash"
          >
            <Square aria-hidden className="size-3.5 fill-current" />
          </button>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={!value.trim() || locked}
            aria-label="Send question"
            className={cn(
              "flex size-9 shrink-0 items-center justify-center rounded-md",
              "bg-accent text-white transition-opacity disabled:opacity-40",
            )}
          >
            <ArrowUp aria-hidden className="size-4" />
          </button>
        )}
      </div>
    </div>
  );
}
