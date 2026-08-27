"use client";

import { useState, useTransition, useRef, useEffect } from "react";
import { toast } from "sonner";
import { Bot, Send, Trash2, User } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { sendAdvisorMessage, clearAdvisorConversation } from "@/app/(app)/ai-advisor/actions";

type StoredMessage = { role: "user" | "assistant"; content: string; createdAt: string };

const SUGGESTIONS = [
  "What should I focus on this month?",
  "What are my biggest weaknesses for my primary target?",
  "Which projects should I highlight in my MBA application?",
  "Create a 90-day development plan.",
];

export function AdvisorChat({ initialMessages }: { initialMessages: StoredMessage[] }) {
  const [messages, setMessages] = useState(initialMessages);
  const [input, setInput] = useState("");
  const [isPending, startTransition] = useTransition();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = (text: string) => {
    if (!text.trim() || isPending) return;
    const optimistic: StoredMessage = { role: "user", content: text, createdAt: new Date().toISOString() };
    setMessages((prev) => [...prev, optimistic]);
    setInput("");
    startTransition(async () => {
      const result = await sendAdvisorMessage(text);
      if (result.ok && result.messages) {
        setMessages(result.messages);
      } else {
        toast.error(result.error ?? "Something went wrong");
        setMessages((prev) => prev.filter((m) => m !== optimistic));
      }
    });
  };

  const clear = () => {
    startTransition(async () => {
      const result = await clearAdvisorConversation();
      if (result.ok) setMessages([]);
    });
  };

  return (
    <div className="flex h-[65vh] flex-col rounded-xl border bg-card">
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <Bot className="size-8 text-muted-foreground" />
            <p className="max-w-sm text-sm text-muted-foreground">
              Ask about your readiness gaps, which projects to highlight, or what to prioritize next.
              Answers are grounded only in the data you&apos;ve logged.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-full border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {messages.map((m, i) => (
              <div key={i} className={cn("flex gap-3", m.role === "user" && "flex-row-reverse")}>
                <div
                  className={cn(
                    "flex size-7 shrink-0 items-center justify-center rounded-full",
                    m.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
                  )}
                >
                  {m.role === "user" ? <User className="size-3.5" /> : <Bot className="size-3.5" />}
                </div>
                <div
                  className={cn(
                    "max-w-[80%] whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-sm",
                    m.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted",
                  )}
                >
                  {m.content}
                </div>
              </div>
            ))}
            {isPending && (
              <div className="flex gap-3">
                <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
                  <Bot className="size-3.5" />
                </div>
                <div className="rounded-2xl bg-muted px-3.5 py-2 text-sm text-muted-foreground">Thinking…</div>
              </div>
            )}
          </div>
        )}
      </div>
      <div className="flex items-end gap-2 border-t p-3">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
          placeholder="Ask your advisor…"
          rows={1}
          className="min-h-9 flex-1 resize-none"
        />
        <Button size="icon" onClick={() => send(input)} disabled={isPending || !input.trim()}>
          <Send className="size-4" />
        </Button>
        {messages.length > 0 && (
          <Button variant="ghost" size="icon" onClick={clear} disabled={isPending} aria-label="Clear conversation">
            <Trash2 className="size-4" />
          </Button>
        )}
      </div>
    </div>
  );
}
