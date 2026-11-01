"use client";
import { useLocale, useTranslations } from "next-intl";
import { useRef, useState } from "react";
import { ScamResult } from "@/components/cards/Cards";
import { Button, Field, Notice, Textarea } from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function ScamForm() {
  const t = useTranslations("scam");
  const tc = useTranslations("common");
  const locale = useLocale();
  const { token } = useAuth();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [fileCount, setFileCount] = useState(0);
  const files = useRef<HTMLInputElement>(null);

  async function check(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    const form = new FormData();
    form.set("text", text);
    form.set("locale", locale);
    for (const f of Array.from(files.current?.files ?? [])) form.append("files", f);
    try {
      setRes(await api<any>("/scam-check", { token, form, method: "POST" }));
    } catch (e: any) {
      setErr(e.status === 429 ? e.message : tc("error"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-4">
      <form onSubmit={check} className="space-y-3">
        <Textarea rows={6} dir="auto" value={text} onChange={(e) => setText(e.target.value)} placeholder={t("placeholder")} aria-label={t("placeholder")} />
        <Field label={t("upload")}>
          <input ref={files} type="file" multiple accept="image/jpeg,image/png,image/webp,application/pdf" className="block w-full text-sm" onChange={(e) => setFileCount(e.target.files?.length ?? 0)} />
        </Field>
        <p className="text-sm text-ink-2">{t("privacy")}</p>
        <Button size="lg" disabled={busy || (!text.trim() && fileCount === 0)}>{busy ? tc("loading") : t("check")}</Button>
      </form>
      {err && <Notice tone="bad">{err}</Notice>}
      {res && (
        <div className="space-y-3">
          {res.result.files_note && <Notice>{t("filesNotRead")}</Notice>}
          <ScamResult r={res.result} />
          <Link href="/chat" className="inline-flex min-h-12 items-center rounded-xl bg-brand px-5 text-brand-ink">{t("cta")}</Link>
        </div>
      )}
    </div>
  );
}
