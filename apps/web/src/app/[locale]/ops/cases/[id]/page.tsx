"use client";
import { Copy, Eye } from "lucide-react";
import { useTranslations } from "next-intl";
import { use, useState } from "react";
import { QuoteCard } from "@/components/cards/Cards";
import { OpsShell } from "@/components/ops/OpsShell";
import { useOps } from "@/components/ops/useOps";
import { Badge, Button, Card, Field, Input, Notice, Select, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime, money } from "@/lib/format";

function CopyButton({ value }: { value: string }) {
  const t = useTranslations("ops");
  const [ok, setOk] = useState(false);
  return (
    <button type="button" className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-0.5 text-xs hover:bg-surface-2"
      onClick={() => navigator.clipboard.writeText(value).then(() => { setOk(true); setTimeout(() => setOk(false), 1200); })}>
      <Copy aria-hidden className="size-3" />{ok ? t("copied") : t("copy")}
    </button>
  );
}

export default function OpsCase({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("ops");
  const { data: b, error, call, token } = useOps<any>(`/ops/cases/${id}`);
  const [msg, setMsg] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  const [ids, setIds] = useState<Record<string, any>>({});
  const [form, setForm] = useState({ reference: "", portal: "gov.uk", bankRef: "", partnerRef: "", items: "", note: "", noteVisible: false, status: "in_process", when: "", where: "", refund: "", reason: "" });
  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));
  const run = async (fn: () => Promise<unknown>) => {
    setMsg(null);
    try { await fn(); setMsg({ tone: "good", text: "✓" }); } catch (e: any) { setMsg({ tone: "bad", text: e.message }); }
  };
  if (!b) return <OpsShell error={error}><p>…</p></OpsShell>;
  const c = b.case;
  const awaitingOps = b.actions.filter((a: any) => a.status === "awaiting_ops");
  const approved = b.actions.filter((a: any) => a.status === "approved");
  const submitAction = approved.find((a: any) => a.kind === "submit_visa");
  const pay = b.payments.find((p: any) => p.direction === "in" && p.status === "received");
  return (
    <OpsShell error={error}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-xl font-semibold">{c.service_type} {c.destination_country ?? ""}</h2>
        <Badge tone="brand">{c.status}</Badge>
        {c.strength_rating && <Badge tone={c.strength_rating === "strong" ? "good" : c.strength_rating === "fair" ? "warn" : "bad"}>{c.strength_rating}</Badge>}
      </div>
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}

      <Card className="space-y-2">
        <h3 className="font-semibold">{t("actions")}</h3>
        {awaitingOps.length === 0 && approved.length === 0 && <p className="text-ink-2">{t("noActions")}</p>}
        {awaitingOps.map((a: any) => (
          <div key={a.action_id} className="flex flex-wrap items-center gap-2 rounded-xl bg-surface-2 p-3">
            <Badge tone="warn">{a.kind}</Badge><span className="flex-1">{a.summary_en}</span>
            <Button size="sm" onClick={() => run(() => call(`/ops/actions/${a.action_id}/approve`, { approve: true }))}>{t("approve")}</Button>
            <Button size="sm" variant="secondary" onClick={() => { const r = window.prompt(t("reason")); if (r) run(() => call(`/ops/actions/${a.action_id}/approve`, { approve: false, reason: r })); }}>{t("reject")}</Button>
          </div>
        ))}
        {approved.map((a: any) => (
          <div key={a.action_id} className="flex flex-wrap items-center gap-2 rounded-xl bg-good-soft p-3">
            <Badge tone="good">{a.kind} · {t("approved")}</Badge><span className="flex-1">{a.summary_en}</span>
            {a.kind === "issue_ticket" && <Button size="sm" onClick={() => run(() => call(`/ops/cases/${id}/issue-ticket`, { action_id: a.action_id }))}>{t("issueTicket")}</Button>}
            {a.kind === "book_hotel" && <Button size="sm" onClick={() => run(() => call(`/ops/cases/${id}/book-hotel`, { action_id: a.action_id }))}>{t("bookHotel")}</Button>}
            {a.kind === "refund" && <Button size="sm" onClick={() => run(() => call(`/ops/cases/${id}/refund/${a.action_id}/execute`, {}))}>{t("executeRefund")}</Button>}
          </div>
        ))}
      </Card>

      {b.pack && (
        <Card className="space-y-3">
          <h3 className="font-semibold">{t("packCopy")}</h3>
          {b.pack.content.applicants.map((ap: any) => (
            <div key={ap.traveller_id} className="space-y-2">
              <div className="flex items-center gap-2">
                <h4 className="font-medium">{ap.name}</h4>
                <Button size="sm" variant="secondary" onClick={() => run(async () => setIds({ ...ids, [ap.traveller_id]: await api(`/ops/travellers/${ap.traveller_id}/sensitive?case_id=${id}`, { token }) }))}>
                  <Eye aria-hidden className="size-4" />{t("reveal")}
                </Button>
              </div>
              <table className="w-full text-sm">
                <tbody>
                  {ap.form_data.map((f: any, i: number) => {
                    const real = f.label === "Passport number" && ids[ap.traveller_id]?.passport_number;
                    const v = String(real || f.value || "");
                    return (
                      <tr key={i} className="border-t border-line">
                        <td className="w-48 py-1 pe-2 text-ink-2">{f.section}</td>
                        <td className="w-64 py-1 pe-2">{f.label}</td>
                        <td className="py-1 pe-2 font-mono">{v}</td>
                        <td className="py-1">{v && <CopyButton value={v} />}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ))}
          {submitAction && (
            <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); run(() => call(`/ops/cases/${id}/submission`, { action_id: submitAction.action_id, reference: form.reference, portal: form.portal })); }}>
              <Field label={t("enterReference")}><Input required className="font-mono" value={form.reference} onChange={(e) => set("reference", e.target.value)} /></Field>
              <Field label={t("portal")}><Input value={form.portal} onChange={(e) => set("portal", e.target.value)} /></Field>
              <Button type="submit">{t("recordSubmission")}</Button>
            </form>
          )}
        </Card>
      )}

      {b.documents.length > 0 && (
        <Card className="space-y-2">
          <h3 className="font-semibold">{t("documents")}</h3>
          {b.documents.map((d: any) => (
            <div key={d.id} className="flex flex-wrap items-center gap-2 text-sm">
              <Badge tone={d.review_status === "ok" ? "good" : d.review_status === "issues" ? "bad" : "neutral"}>{d.review_status}</Badge>
              <span>{d.doc_type}</span>
              <button className="text-brand underline" onClick={() => run(async () => { const r = await api<any>(`/documents/${d.id}/url`, { token }); window.open(r.url, "_blank", "noopener"); })}>{t("openLink")}</button>
              {(d.review_findings || []).map((f: any) => <span key={f.code} className="text-bad">{f.code}</span>)}
            </div>
          ))}
        </Card>
      )}

      <Card className="space-y-3">
        <h3 className="font-semibold">{t("payments")}</h3>
        {b.payments.map((p: any) => <p key={p.id} className="text-sm">{money(p.amount_minor, p.currency, "en")} · {p.direction} · <Badge>{p.status}</Badge> · {p.provider_ref}</p>)}
        {pay && (
          <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); run(() => call(`/ops/payments/${pay.id}/verify`, { bank_reference: form.bankRef })); }}>
            <Field label={t("bankRef")}><Input required value={form.bankRef} onChange={(e) => set("bankRef", e.target.value)} /></Field>
            <Button type="submit">{t("verifyPayment")}</Button>
          </form>
        )}
        <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); run(() => call(`/ops/cases/${id}/refund`, { amount_minor: Math.round(Number(form.refund) * 100), reason: form.reason })); }}>
          <Field label={t("amount")}><Input inputMode="numeric" value={form.refund} onChange={(e) => set("refund", e.target.value)} /></Field>
          <Field label={t("reason")}><Input value={form.reason} onChange={(e) => set("reason", e.target.value)} /></Field>
          <Button type="submit" variant="secondary">{t("refund")}</Button>
          <span className="text-sm text-ink-2">{t("policyAllows", { percent: b.refund?.percent ?? 0 })}</span>
        </form>
      </Card>

      {c.service_type === "umrah_package" && approved.find((a: any) => a.kind === "book_umrah") && (
        <Card>
          <form className="space-y-2" onSubmit={(e) => {
            e.preventDefault();
            const items = form.items.split("\n").filter(Boolean).map((l) => { const [kind, reference, doc] = l.split(",").map((x) => x.trim()); return { kind, reference, documents: doc ? [{ name: doc }] : [] }; });
            run(() => call(`/ops/cases/${id}/partner-booking`, { action_id: approved.find((a: any) => a.kind === "book_umrah").action_id, partner_ref: form.partnerRef, items }));
          }}>
            <h3 className="font-semibold">{t("partnerBooking")}</h3>
            <Field label={t("partnerRef")}><Input required value={form.partnerRef} onChange={(e) => set("partnerRef", e.target.value)} /></Field>
            <Field label={t("items")}><Textarea rows={5} className="font-mono text-sm" value={form.items} onChange={(e) => set("items", e.target.value)} placeholder={"visa_application, UMR-123, Umrah e-visa\nflight, PNR123, E-tickets\nhotel, MKH-1, Makkah voucher"} /></Field>
            <Button type="submit">{t("partnerBooking")}</Button>
          </form>
        </Card>
      )}

      <Card>
        <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); run(() => call(`/ops/cases/${id}/status`, { status: form.status, when: form.when || null, where: form.where || null, note: form.note || null })); }}>
          <Field label={t("setStatus")}><Select value={form.status} onChange={(e) => set("status", e.target.value)}>{["biometrics_scheduled", "in_process", "decision_approved", "decision_refused", "completed", "cancelled"].map((s) => <option key={s}>{s}</option>)}</Select></Field>
          {form.status === "biometrics_scheduled" && <><Field label={t("when")}><Input value={form.when} onChange={(e) => set("when", e.target.value)} placeholder="2027-01-03 10:00" /></Field><Field label={t("where")}><Input value={form.where} onChange={(e) => set("where", e.target.value)} placeholder="VFS Lahore" /></Field></>}
          <Button type="submit" variant="secondary">{t("setStatus")}</Button>
        </form>
        <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); run(() => call(`/ops/cases/${id}/notes`, { note: form.note, visible_to_user: form.noteVisible })); }}>
          <Field label={t("note")}><Input value={form.note} onChange={(e) => set("note", e.target.value)} /></Field>
          <label className="flex items-center gap-2 pb-2"><input type="checkbox" checked={form.noteVisible} onChange={(e) => set("noteVisible", e.target.checked)} />{t("visibleToUser")}</label>
          <Button type="submit" variant="secondary">{t("addNote")}</Button>
        </form>
      </Card>

      {b.quote && <QuoteCard q={b.quote} />}
      {c.assessment && (
        <Card><h3 className="mb-1 font-semibold">{t("aiAssessment")}</h3><pre className="max-h-64 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(c.assessment.factors?.map((f: any) => `${f.impact} ${f.code}`), null, 1)}</pre></Card>
      )}
      <Card>
        <h3 className="mb-2 font-semibold">{t("events")}</h3>
        <ol className="space-y-1 text-sm">
          {b.events.map((e: any) => <li key={e.id}><span className="text-ink-2">{dateTime(e.created_at, "en")} · {e.actor_type}</span> {!e.visible_to_user && <Badge tone="warn">{t("internal")}</Badge>} {e.message_en}</li>)}
        </ol>
      </Card>
    </OpsShell>
  );
}
