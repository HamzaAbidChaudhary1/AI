"use client";
import { CheckCircle2, Loader2, Send, Square } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";
import { CardRenderer, Citation, type CardData } from "@/components/cards/Cards";
import { Button, Notice, Textarea } from "@/components/ui";
import { streamSse } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/format";

type Step = { step: string; step_ur: string; done: boolean };
type Msg = { role: "user" | "assistant"; text: string; steps: Step[]; citations: any[]; cards: CardData[]; error?: string; job?: { eta_seconds: number } };

const SESSION_KEY = "rahbar.chatSession";

/** Per-tab chat session id (sessionStorage); a fresh one if storage is unavailable. */
function loadSession(): string {
  if (typeof window === "undefined") return "";
  try {
    const existing = sessionStorage.getItem(SESSION_KEY);
    if (existing) return existing;
    const s = newSessionId();
    sessionStorage.setItem(SESSION_KEY, s);
    return s;
  } catch {
    return newSessionId();
  }
}

function newSessionId() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

// A bracketed English term "(Proof of funds)" is one unit; otherwise a Latin run without parens or colons,
// so the Urdu label's ":" and brackets keep their RTL position.
const LATIN_RUN = /(\([^()\u0600-\u06FF]+\)|[A-Za-z0-9£$€][A-Za-z0-9£$€ ,.;'’&/%+-]*[A-Za-z0-9.%])/g;

/** In Urdu text, isolate English runs (fees, official terms) so bidi doesn't reorder their punctuation. */
function isolate(text: string, rtl: boolean) {
  if (!rtl) return text;
  return text.split(LATIN_RUN).map((part, k) => (k % 2 === 1 ? <bdi key={k} className="latin">{part}</bdi> : part));
}

function inline(line: string, rtl = false) {
  // minimal, safe formatting: **bold** only. Text is rendered as React text nodes (no HTML injection).
  return line.split(/(\*\*[^*]+\*\*)/g).map((p, j) => (p.startsWith("**") && p.endsWith("**") ? <strong key={j}>{isolate(p.slice(2, -2), rtl)}</strong> : <span key={j}>{isolate(p, rtl)}</span>));
}

function renderText(text: string, rtl = false) {
  return text.split("\n").map((line, i) => {
    const item = line.match(/^\s*-\s+(.*)$/);
    if (item) return <li key={i} className="ms-5 list-disc">{inline(item[1] ?? "", rtl)}</li>;
    return line.trim() ? <p key={i}>{inline(line, rtl)}</p> : <div key={i} className="h-2" />;
  });
}

export function Chat({ initialPayload, initialMessage, caseId, hideIntro }: { initialPayload?: Record<string, unknown>; initialMessage?: string; caseId?: string; hideIntro?: boolean }) {
  const t = useTranslations("chat");
  const tc = useTranslations("common");
  const locale = useLocale() as "en" | "ur";
  const { token, ready } = useAuth();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [session] = useState<string>(loadSession);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const started = useRef(false);


  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [msgs]);

  const update = (fn: (m: Msg) => Msg) => setMsgs((all) => all.map((m, i) => (i === all.length - 1 ? fn(m) : m)));

  const send = useCallback(
    async (text: string, payload?: Record<string, unknown>, resume?: Record<string, unknown>) => {
      if (busy || !session) return;
      setBusy(true);
      setMsgs((m) => [
        ...m,
        ...(text ? [{ role: "user" as const, text, steps: [], citations: [], cards: [] }] : []),
        { role: "assistant", text: "", steps: [], citations: [], cards: [] },
      ]);
      const ctrl = new AbortController();
      abort.current = ctrl;
      try {
        await streamSse("/chat", { message: text, locale, session_id: session, case_id: caseId, payload: payload ?? {}, resume }, token, (e) => {
          switch (e.event) {
            case "progress":
              update((m) => ({ ...m, steps: [...m.steps.map((s) => ({ ...s, done: true })), { ...e.data, done: false }] }));
              break;
            case "token":
              update((m) => ({ ...m, text: m.text + e.data.text }));
              break;
            case "citation":
              update((m) => (m.citations.some((c) => c.url === e.data.url) ? m : { ...m, citations: [...m.citations, e.data] }));
              break;
            case "card":
              update((m) => ({ ...m, cards: [...m.cards, e.data] }));
              break;
            case "job":
              update((m) => ({ ...m, job: e.data }));
              break;
            case "error":
              update((m) => ({ ...m, error: e.data.message }));
              break;
            case "done":
              update((m) => ({ ...m, steps: m.steps.map((s) => ({ ...s, done: true })) }));
              break;
          }
        }, ctrl.signal);
      } catch (err: any) {
        if (err?.name !== "AbortError") update((m) => ({ ...m, error: tc("error") }));
      } finally {
        setBusy(false);
        abort.current = null;
      }
    },
    [busy, session, locale, caseId, token, tc],
  );

  useEffect(() => {
    if (!started.current && session && ready && (initialPayload || initialMessage)) {
      started.current = true;
      send(initialMessage ?? "", initialPayload);
    }
  }, [session, ready, initialPayload, initialMessage, send]);

  function submit(e?: React.FormEvent) {
    e?.preventDefault();
    const v = input.trim();
    if (!v) return;
    setInput("");
    send(v);
  }

  const examples = [t("ex1"), t("ex2"), t("ex3"), t("ex4")];

  return (
    <div className="flex flex-col gap-4">
      {msgs.length === 0 && !hideIntro && (
        <div className="space-y-3">
          <p className="text-ink-2">{t("intro")}</p>
          <p className="text-sm font-medium text-ink-2">{t("examples")}</p>
          <div className="flex flex-wrap gap-2">
            {examples.map((ex) => (
              <button key={ex} onClick={() => send(ex)} className="rounded-full border border-line bg-surface px-3 py-2 text-start hover:bg-surface-2">{ex}</button>
            ))}
          </div>
        </div>
      )}
      <div className="space-y-4" aria-live="polite">
        {msgs.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="ms-auto max-w-[85%] rounded-2xl rounded-ee-sm bg-brand px-4 py-2 text-brand-ink">{m.text}</div>
          ) : (
            <div key={i} className="space-y-3">
              {m.steps.length > 0 && (
                <ul className="space-y-1 text-sm text-ink-2" aria-label={t("working")}>
                  {m.steps.map((s, j) => (
                    <li key={j} className="flex items-center gap-2">
                      {s.done ? <CheckCircle2 aria-hidden className="size-4 text-good" /> : <Loader2 aria-hidden className="size-4 animate-spin" />}
                      {locale === "ur" ? s.step_ur : s.step}
                    </li>
                  ))}
                </ul>
              )}
              {m.text && <div className="space-y-1 rounded-2xl rounded-es-sm bg-surface p-4 shadow-sm">{renderText(m.text, locale === "ur")}</div>}
              {m.job && <Notice tone="brand">{t("jobRunning", { seconds: m.job.eta_seconds })}</Notice>}
              {m.error && <Notice tone="bad">{m.error}</Notice>}
              {m.citations.length > 0 && (
                <div className="space-y-1">
                  <p className="text-sm font-medium text-ink-2">{t("sources")}</p>
                  <div className="flex flex-wrap gap-2">{m.citations.map((c) => <Citation key={c.url} c={c} />)}</div>
                </div>
              )}
              {m.cards.map((c, j) => <CardRenderer key={j} card={c} send={send} />)}
            </div>
          ),
        )}
        <div ref={bottom} />
      </div>
      <form onSubmit={submit} className="sticky bottom-0 flex items-end gap-2 bg-bg py-3">
        <Textarea
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
          placeholder={t("placeholder")}
          aria-label={t("placeholder")}
          className="min-h-14 flex-1 resize-none"
          dir="auto"
        />
        {busy ? (
          <Button type="button" variant="secondary" size="lg" onClick={() => abort.current?.abort()} aria-label={t("stop")}><Square className="size-5" /></Button>
        ) : (
          <Button type="submit" size="lg" disabled={!input.trim()} aria-label={t("send")}><Send className={cn("size-5", locale === "ur" && "-scale-x-100")} /></Button>
        )}
      </form>
    </div>
  );
}
