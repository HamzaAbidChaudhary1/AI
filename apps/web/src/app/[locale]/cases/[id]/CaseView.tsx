"use client";
import { CheckCircle2, Circle, Download, FileText, Radio } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";
import { ConfirmAction, QuoteCard } from "@/components/cards/Cards";
import { Badge, Button, Card, Field, Notice, Select } from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, dateTime, money } from "@/lib/format";
import { supabaseBrowser } from "@/lib/supabase/client";

const VISA_STEPS = ["quoted", "accepted", "collecting_documents", "documents_review", "pack_ready", "awaiting_user_confirmation", "submitted", "in_process", "decision_approved"];
const BOOK_STEPS = ["quoted", "accepted", "booked", "completed"];
const UMRAH_STEPS = ["quoted", "accepted", "collecting_documents", "booked", "completed"];

export function CaseView({ id }: { id: string }) {
  const t = useTranslations();
  const locale = useLocale();
  const { token, ready } = useAuth();
  const [b, setB] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const load = useCallback(() => {
    if (!token) return;
    api<any>(`/cases/${id}`, { token }).then(setB).catch((e) => setErr(e.message));
  }, [id, token]);

  useEffect(load, [load]);
  useEffect(() => {
    // Live timeline: Supabase Realtime on case_events (RLS limits rows to this user); polling fallback.
    const sb = supabaseBrowser();
    if (sb && token) {
      sb.realtime.setAuth(token);
      const ch = sb.channel(`case:${id}`).on("postgres_changes", { event: "INSERT", schema: "public", table: "case_events", filter: `case_id=eq.${id}` }, load).subscribe((s) => setLive(s === "SUBSCRIBED"));
      return () => { sb.removeChannel(ch); };
    }
    const iv = setInterval(load, 15000);
    return () => clearInterval(iv);
  }, [id, token, load]);

  if (!ready) return <p>{t("common.loading")}</p>;
  if (!token) return <Notice tone="brand"><Link href="/login" className="underline">{t("common.signInToContinue")}</Link></Notice>;
  if (err) return <Notice tone="bad">{err}</Notice>;
  if (!b) return <p>{t("common.loading")}</p>;
  const c = b.case;
  const steps = c.service_type === "visit_visa" ? VISA_STEPS : c.service_type === "umrah_package" ? UMRAH_STEPS : BOOK_STEPS;
  const cur = steps.indexOf(c.status);
  const openActions = b.actions.filter((a: any) => a.status === "awaiting_user");
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-semibold">{c.service_type.replace("_", " ")} {c.destination_country ? `· ${c.destination_country}` : ""}</h1>
        <Badge tone="brand">{t(`status.${c.status}` as "status.quoted")}</Badge>
        {live && <Badge tone="good"><Radio aria-hidden className="size-3.5" />{t("cases.live")}</Badge>}
      </div>
      <ol className="flex flex-wrap gap-x-4 gap-y-2" aria-label="progress">
        {steps.map((s, i) => (
          <li key={s} className={cn("flex items-center gap-1.5 text-sm", i <= cur ? "text-good" : "text-ink-2")}>
            {i <= cur ? <CheckCircle2 aria-hidden className="size-4" /> : <Circle aria-hidden className="size-4" />}
            {t(`status.${s}` as "status.quoted")}
          </li>
        ))}
      </ol>
      {openActions.map((a: any) => <ConfirmAction key={a.action_id} a={a} onDone={load} />)}
      {b.quote && <QuoteCard q={b.quote} onAccepted={load} />}
      <PaymentBlock b={b} reload={load} />
      {(c.service_type === "visit_visa" || c.service_type === "umrah_package") && ["accepted", "collecting_documents", "documents_review", "pack_ready", "awaiting_user_confirmation"].includes(c.status) && (
        <DocumentsBlock b={b} reload={load} />
      )}
      {b.pack && <PackBlock b={b} reload={load} />}
      {["flight", "hotel", "umrah_package"].includes(c.service_type) && ["accepted", "collecting_documents", "documents_review"].includes(c.status) && !b.actions.some((a: any) => ["issue_ticket", "book_hotel", "book_umrah"].includes(a.kind)) && (
        <Button onClick={() => api(`/cases/${id}/booking-confirmation`, { token, method: "POST" }).then(load).catch((e) => setErr(e.message))}>{t("cases.bookConfirm")}</Button>
      )}
      {b.bookings.length > 0 && (
        <Card>
          <h2 className="mb-2 text-lg font-semibold">{t("cases.bookings")}</h2>
          <ul className="space-y-2">
            {b.bookings.map((bk: any) => (
              <li key={bk.id} className="flex flex-wrap items-center gap-2">
                <Badge>{bk.kind.replace("_", " ")}</Badge>
                <span className="latin font-mono text-lg font-semibold tracking-wide">{bk.provider_ref}</span>
                <span className="text-sm text-ink-2">{bk.provider} · {bk.status}</span>
                {(bk.documents || []).map((d: any, i: number) => <span key={i} className="inline-flex items-center gap-1 text-sm"><FileText aria-hidden className="size-4" />{d.name}</span>)}
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Card>
        <h2 className="mb-3 text-lg font-semibold">{t("cases.timeline")}</h2>
        <ol className="relative space-y-4 border-s-2 border-line ps-5">
          {b.events.map((e: any) => (
            <li key={e.id} className="relative">
              <span className="absolute -start-[1.65rem] top-1.5 size-3 rounded-full bg-brand" aria-hidden />
              <p>{locale === "ur" ? e.message_ur : e.message_en}</p>
              <p className="text-sm text-ink-2">{t(`cases.actor_${e.actor_type}` as "cases.actor_ai")} · {dateTime(e.created_at, locale)}</p>
            </li>
          ))}
        </ol>
      </Card>
      {b.refund?.policy_en && (
        <Card>
          <h2 className="mb-2 text-lg font-semibold">{t("cases.refund")}</h2>
          <p>{locale === "ur" ? b.refund.policy_ur : b.refund.policy_en}</p>
          <p className="mt-2 text-sm text-ink-2">{t("cases.refundNow", { percent: b.refund.percent })}</p>
        </Card>
      )}
    </div>
  );
}

function PaymentBlock({ b, reload }: { b: any; reload: () => void }) {
  const t = useTranslations("cases");
  const locale = useLocale();
  const { token } = useAuth();
  const file = useRef<HTMLInputElement>(null);
  const [instr, setInstr] = useState<any>(null);
  const q = b.quote;
  if (!q || q.status !== "accepted") return null;
  const pay = b.payments.find((p: any) => p.direction === "in");
  const pending = pay && ["pending"].includes(pay.status);
  const ev = b.events.find((e: any) => e.event_type === "payment_requested");
  const details = instr?.instructions ?? ev?.data?.instructions;
  async function request() {
    setInstr(await api(`/quotes/${q.quote_id}/payment`, { token, method: "POST" }));
    reload();
  }
  async function upload() {
    const f = file.current?.files?.[0];
    if (!f || !pay) return;
    const form = new FormData();
    form.set("file", f);
    await api(`/payments/${pay.id}/receipt`, { token, form, method: "POST" });
    reload();
  }
  return (
    <Card className="space-y-3">
      <h2 className="text-lg font-semibold">{t("payment")}</h2>
      {!pay && <Button onClick={request}>{t("requestPayment")}</Button>}
      {pay && <p className="latin">{money(pay.amount_minor, pay.currency, locale)} · <Badge tone={pay.status === "verified" ? "good" : "warn"}>{pay.status}</Badge></p>}
      {details && pending && (
        <dl className="latin grid grid-cols-[10rem_1fr] gap-1 rounded-xl bg-surface-2 p-3 text-sm">
          <dt>{t("accountTitle")}</dt><dd>{details.account_title}</dd>
          <dt>{t("iban")}</dt><dd className="font-mono">{details.iban}</dd>
          <dt>{t("bank")}</dt><dd>{details.bank}</dd>
          <dt>{t("reference")}</dt><dd className="font-mono font-semibold">{details.payment_reference}</dd>
        </dl>
      )}
      {pending && (
        <div className="flex flex-wrap items-end gap-2">
          <Field label={t("uploadReceipt")}><input ref={file} type="file" accept="image/*,application/pdf" className="block text-sm" /></Field>
          <Button variant="secondary" onClick={upload}>{t("upload")}</Button>
        </div>
      )}
    </Card>
  );
}

function DocumentsBlock({ b, reload }: { b: any; reload: () => void }) {
  const t = useTranslations();
  const locale = useLocale();
  const { token } = useAuth();
  const file = useRef<HTMLInputElement>(null);
  const [docType, setDocType] = useState(b.checklist[0]?.doc_type ?? "passport");
  const [traveller, setTraveller] = useState<string>(b.travellers[0]?.id ?? "");
  const [msg, setMsg] = useState<string | null>(null);
  const [mine, setMine] = useState<any[]>([]);
  useEffect(() => {
    if (b.travellers.length === 0 && token) api<any[]>("/travellers", { token }).then(setMine).catch(() => {});
  }, [b.travellers.length, token]);
  async function upload() {
    const f = file.current?.files?.[0];
    if (!f) return;
    const form = new FormData();
    form.set("file", f);
    form.set("doc_type", docType);
    if (traveller) form.set("traveller_id", traveller);
    try {
      await api(`/cases/${b.case.id}/documents`, { token, form, method: "POST" });
      if (file.current) file.current.value = "";
      reload();
    } catch (e: any) {
      setMsg(e.message);
    }
  }
  async function review() {
    await api(`/cases/${b.case.id}/review`, { token, method: "POST" });
    setMsg(t("cases.reviewStarted"));
    setTimeout(reload, 4000);
  }
  async function makePack() {
    try {
      await api(`/cases/${b.case.id}/pack`, { token, method: "POST" });
      reload();
    } catch (e: any) {
      setMsg(e.message);
    }
  }
  const uploaded = new Set(b.documents.map((d: any) => d.doc_type));
  return (
    <Card className="space-y-3">
      <h2 className="text-lg font-semibold">{t("cases.documents")}</h2>
      {b.travellers.length === 0 && mine.length > 0 && (
        <div className="flex flex-wrap items-end gap-2">
          <span>{t("cases.addTravellers")}:</span>
          {mine.map((tr) => <Button key={tr.id} size="sm" variant="secondary" onClick={() => api(`/cases/${b.case.id}/travellers`, { token, body: { traveller_ids: [tr.id] } }).then(reload)}>{t("cases.add")} {tr.full_name_as_passport}</Button>)}
        </div>
      )}
      <ul className="space-y-1">
        {b.checklist.map((i: any) => (
          <li key={i.doc_type} className="flex items-center gap-2">
            {uploaded.has(i.doc_type) ? <CheckCircle2 aria-hidden className="size-5 text-good" /> : <Circle aria-hidden className="size-5 text-ink-2" />}
            {locale === "ur" ? i.ur : i.en}{i.optional ? ` (${t("common.optional")})` : ""}
          </li>
        ))}
      </ul>
      {b.documents.some((d: any) => d.review_findings?.length) && (
        <div className="space-y-2">
          <h3 className="font-medium">{t("cases.findings")}</h3>
          {b.documents.flatMap((d: any) => d.review_findings || []).filter((f: any, i: number, all: any[]) => all.findIndex((x) => x.code === f.code) === i).map((f: any) => (
            <Notice key={f.code} tone={f.severity === "blocker" ? "bad" : "warn"}>{locale === "ur" ? f.ur : f.en}</Notice>
          ))}
        </div>
      )}
      <div className="grid gap-2 sm:grid-cols-3">
        <Field label={t("cases.docType")}>
          <Select value={docType} onChange={(e) => setDocType(e.target.value)}>
            {b.checklist.map((i: any) => <option key={i.doc_type} value={i.doc_type}>{t(`cases.doc_${i.doc_type}` as "cases.doc_passport")}</option>)}
          </Select>
        </Field>
        {b.travellers.length > 1 && (
          <Field label={t("cases.traveller")}>
            <Select value={traveller} onChange={(e) => setTraveller(e.target.value)}>{b.travellers.map((tr: any) => <option key={tr.id} value={tr.id}>{tr.full_name_as_passport}</option>)}</Select>
          </Field>
        )}
        <Field label={t("cases.chooseFile")}><input ref={file} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" className="block text-sm" /></Field>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={upload}>{t("cases.upload")}</Button>
        {b.documents.length > 0 && <Button variant="secondary" onClick={review}>{t("cases.review")}</Button>}
        {b.case.status === "documents_review" && b.case.service_type === "visit_visa" && <Button onClick={makePack}>{t("cases.makePack")}</Button>}
      </div>
      {msg && <Notice tone="brand">{msg}</Notice>}
    </Card>
  );
}

function PackBlock({ b, reload }: { b: any; reload: () => void }) {
  const t = useTranslations("cases");
  const { token } = useAuth();
  const p = b.pack.content;
  const [err, setErr] = useState<string | null>(null);
  return (
    <Card className="space-y-3">
      <h2 className="text-lg font-semibold">{t("pack")} v{b.pack.version}</h2>
      {p.applicants.map((a: any) => (
        <details key={a.traveller_id} className="rounded-xl bg-surface-2 p-3">
          <summary className="cursor-pointer font-medium latin">{a.name}</summary>
          <h3 className="mt-2 font-medium">{t("formData")}</h3>
          <dl className="latin grid gap-x-3 gap-y-1 text-sm sm:grid-cols-[16rem_1fr]">
            {a.form_data.map((f: any, i: number) => <div key={i} className="contents"><dt className="text-ink-2">{f.label}</dt><dd>{String(f.value ?? "")}</dd></div>)}
          </dl>
          <h3 className="mt-3 font-medium">{t("coverLetter")}</h3>
          <pre className="latin whitespace-pre-wrap rounded-lg bg-surface p-3 text-sm">{a.cover_letter_en}</pre>
        </details>
      ))}
      <h3 className="font-medium">{t("docIndex")}</h3>
      <ol className="latin list-decimal ps-6 text-sm">{p.document_index.map((d: any) => <li key={d.n}>{d.filename}</li>)}</ol>
      {err && <Notice tone="bad">{err}</Notice>}
      {b.case.status === "pack_ready" && (
        <Button size="lg" onClick={() => api(`/cases/${b.case.id}/submit`, { token, method: "POST" }).then(reload).catch((e) => setErr(e.message))}>
          <Download aria-hidden className="size-5" />{t("submitPack")}
        </Button>
      )}
    </Card>
  );
}
