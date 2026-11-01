"use client";
import { AlertTriangle, CheckCircle2, ExternalLink, Info, ShieldAlert, XCircle } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Badge, Button, Card, Field, Input, Notice, Select } from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, dateTime, money } from "@/lib/format";

export type CardData = { type: string; [k: string]: any };
export type SendFn = (text: string, payload?: Record<string, unknown>, resume?: Record<string, unknown>) => void;

const L = (locale: string, en?: string, ur?: string) => (locale === "ur" ? ur || en : en || ur) ?? "";

export function Citation({ c }: { c: { url: string; title: string; verified_at: string; is_test_fixture?: boolean; authority?: string } }) {
  const t = useTranslations("common");
  const locale = useLocale();
  const external = c.url.startsWith("http");
  const inner = (
    <>
      <span className="latin truncate">{c.authority || c.title}</span>
      <span className="text-ink-2">· {t("verified", { date: dateTime(c.verified_at, locale, false) })}</span>
      {c.is_test_fixture ? <Badge tone="warn" className="!py-0 text-xs">{t("testData")}</Badge> : null}
      {external ? <ExternalLink aria-hidden className="size-3.5 shrink-0" /> : null}
    </>
  );
  const cls = "inline-flex max-w-full items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-sm";
  return external ? (
    <a href={c.url} target="_blank" rel="noopener noreferrer" className={cn(cls, "hover:bg-surface-2")} title={c.title}>{inner}</a>
  ) : (
    <span className={cls} title={c.title}>{inner}</span>
  );
}

export function CardRenderer({ card, send }: { card: CardData; send: SendFn }) {
  switch (card.type) {
    case "assessment": return <AssessmentCard a={card} />;
    case "quote": return <QuoteCard q={card} />;
    case "checklist": return <ChecklistCard c={card} />;
    case "profile_form": return <ProfileForm c={card} send={send} />;
    case "scam_check": return <ScamResult r={card} />;
    case "umrah_form": return <UmrahForm c={card} send={send} />;
    case "umrah_options": return <UmrahOptions c={card} send={send} />;
    case "flight_options": return <FlightOptions c={card} send={send} />;
    case "hotel_options": return <HotelOptions c={card} send={send} />;
    case "booking_form": return <BookingForm c={card} send={send} />;
    case "confirm_action": return <ConfirmAction a={card} send={send} />;
    case "login_required": return <LoginRequired />;
    default: return null;
  }
}

function LoginRequired() {
  const t = useTranslations();
  return (
    <Card className="flex flex-wrap items-center gap-3">
      <span className="flex-1">{t("cards.loginRequired")}</span>
      <Link href="/login" className="inline-flex min-h-11 items-center rounded-xl bg-brand px-4 text-brand-ink">{t("nav.login")}</Link>
    </Card>
  );
}

// ------------------------------------------------------------------ assessment
export function AssessmentCard({ a }: { a: CardData }) {
  const t = useTranslations("cards");
  const locale = useLocale();
  const tone = a.rating === "strong" ? "good" : a.rating === "fair" ? "warn" : "bad";
  const neg = a.factors.filter((f: any) => f.impact === "negative");
  const pos = a.factors.filter((f: any) => f.impact === "positive");
  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-lg font-semibold">{t("assessment")}</h3>
        <Badge tone={tone} className="text-base">{t(`rating_${a.rating}` as "rating_strong")}</Badge>
      </div>
      {a.blockers.length > 0 && (
        <div className="space-y-1">
          <h4 className="font-medium text-bad">{t("blockers")}</h4>
          {a.blockers.map((f: any) => <p key={f.code} className="flex gap-2"><XCircle aria-hidden className="mt-1 size-5 shrink-0 text-bad" />{L(locale, f.en, f.ur)}</p>)}
        </div>
      )}
      {neg.length > 0 && (
        <div className="space-y-1">
          <h4 className="font-medium">{t("weaknesses")}</h4>
          {neg.map((f: any) => <p key={f.code} className="flex gap-2"><AlertTriangle aria-hidden className="mt-1 size-5 shrink-0 text-warn" />{L(locale, f.en, f.ur)}</p>)}
        </div>
      )}
      {pos.length > 0 && (
        <div className="space-y-1">
          <h4 className="font-medium">{t("strengths")}</h4>
          {pos.map((f: any) => <p key={f.code} className="flex gap-2"><CheckCircle2 aria-hidden className="mt-1 size-5 shrink-0 text-good" />{L(locale, f.en, f.ur)}</p>)}
        </div>
      )}
      {a.improvements.length > 0 && (
        <div className="space-y-1">
          <h4 className="font-medium">{t("improve")}</h4>
          <ul className="list-disc space-y-1 ps-6">{a.improvements.map((i: any, n: number) => <li key={n}>{L(locale, i.en, i.ur)}</li>)}</ul>
        </div>
      )}
      {a.missing_info.length > 0 && <Notice>{t("missing")}</Notice>}
      <p className="text-sm text-ink-2">{t("ourJudgement")}</p>
    </Card>
  );
}

// ------------------------------------------------------------------ quote
export function QuoteCard({ q, onAccepted }: { q: CardData; onAccepted?: () => void }) {
  const t = useTranslations("cards");
  const tc = useTranslations("common");
  const tcase = useTranslations("cases");
  const locale = useLocale();
  const { token } = useAuth();
  const [status, setStatus] = useState<string>(q.status);
  const [err, setErr] = useState<string | null>(null);
  async function accept() {
    setErr(null);
    try {
      await api(`/quotes/${q.quote_id}/accept`, { token, method: "POST" });
      setStatus("accepted");
      onAccepted?.();
    } catch (e: any) {
      setErr(e.message);
    }
  }
  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-lg font-semibold">{t("quote")} v{q.version}</h3>
        {!q.binding && <Badge tone="warn">{tc("testData")}</Badge>}
      </div>
      <ul className="divide-y divide-line">
        <li className="hidden grid-cols-[1fr_9rem_9rem] gap-3 pb-2 text-sm text-ink-2 sm:grid">
          <span>{t("item")}</span><span>{t("payee")}</span><span className="text-end">{t("amount")}</span>
        </li>
        {q.lines.map((li: any, i: number) => (
          <li key={i} className={cn("grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5 py-2.5 sm:grid-cols-[1fr_9rem_9rem]", li.payee === "rahbar" && "-mx-2 rounded-lg bg-brand-soft/60 px-2")}>
            <div className="min-w-0">
              <div>{L(locale, li.description_en, li.description_ur)}{li.quantity > 1 ? <span className="tabular text-ink-2"> × {li.quantity}</span> : null}</div>
              {li.source_url && <a className="latin text-sm text-brand underline" href={li.source_url} target="_blank" rel="noopener noreferrer">{tc("source")}{li.source_verified_at ? ` · ${tc("verified", { date: dateTime(li.source_verified_at, locale, false) })}` : ""}</a>}
              {li.indicative && <div className="text-sm text-warn">{tc("maybeOutdated")}</div>}
              {li.paid_directly_by_user && <div className="text-sm text-ink-2">{t("paidDirect")}</div>}
            </div>
            <div className="col-start-1 row-start-2 text-sm text-ink-2 sm:col-start-2 sm:row-start-1 sm:text-base sm:text-ink">
              <span className="sm:hidden">{t("payee")}: </span>{t(`payee_${li.payee}` as "payee_rahbar")}
            </div>
            <div className="tabular latin col-start-2 row-span-2 row-start-1 text-end sm:col-start-3 sm:row-span-1">
              <div className="font-medium">{money(li.amount_quote_currency_minor, "PKR", locale)}</div>
              {li.currency !== "PKR" && <div className="text-sm text-ink-2">{money(li.amount_minor, li.currency, locale)}</div>}
            </div>
          </li>
        ))}
        <li className="flex items-baseline justify-between gap-3 pt-3 text-lg font-semibold">
          <span>{t("total")}</span><span className="tabular latin">{money(q.total_minor, q.currency, locale)}</span>
        </li>
        {q.collect_minor !== q.total_minor && (
          <li className="flex justify-between gap-3 text-ink-2"><span>{t("weCollect")}</span><span className="tabular latin">{money(q.collect_minor, q.currency, locale)}</span></li>
        )}
      </ul>
      {Object.keys(q.fx_rates || {}).length > 0 && (
        <p className="latin text-sm text-ink-2">{t("fx")}: {Object.entries(q.fx_rates).map(([k, v]) => `1 ${k} = PKR ${Number(v).toLocaleString("en", { maximumFractionDigits: 2 })}`).join(" · ")}</p>
      )}
      <p className="text-sm text-ink-2">{t("validUntil", { date: dateTime(q.valid_until, locale) })}</p>
      {!q.binding && <Notice>{t("indicative")}</Notice>}
      <p className="text-sm text-ink-2">{tc("noGuarantee")}</p>
      {err && <Notice tone="bad">{err}</Notice>}
      {status === "sent" ? (
        token ? <Button onClick={accept}>{t("acceptQuote")}</Button> : <LoginRequired />
      ) : (
        <Badge tone={status === "accepted" ? "good" : "neutral"}>{status === "accepted" ? t("accepted") : status}</Badge>
      )}
      {status === "accepted" && q.case_id && <Link href={`/cases/${q.case_id}`} className="ms-3 text-brand underline">{tcase("open")}</Link>}
    </Card>
  );
}

function ChecklistCard({ c }: { c: CardData }) {
  const t = useTranslations("cards");
  const locale = useLocale();
  return (
    <Card className="space-y-2">
      <h3 className="text-lg font-semibold">{L(locale, c.title_en, c.title_ur) || t("checklist")}</h3>
      <ul className="space-y-1">{(c.items as string[]).map((it, i) => <li key={i} className="flex gap-2"><CheckCircle2 aria-hidden className="mt-1 size-5 shrink-0 text-brand" /><span className={locale === "ur" ? "latin" : ""}>{it}</span></li>)}</ul>
      {c.citation && <Citation c={c.citation} />}
    </Card>
  );
}

// ------------------------------------------------------------------ profile form
const EMP = ["employed", "self_employed", "business_owner", "retired", "student", "homemaker", "unemployed"] as const;
const DESTS = ["GB", "DE", "TR", "AE", "MY", "SA"];

function codes(s: string) {
  return s.split(/[,\s]+/).map((x) => x.trim().toUpperCase()).filter((x) => /^[A-Z]{2}$/.test(x));
}

function ProfileForm({ c, send }: { c: CardData; send: SendFn }) {
  const t = useTranslations("cards");
  const [f, setF] = useState({ destination: c.destination || "GB", days: c.days || 14, travellers: c.travellers || 1, employment_status: "employed", funds: "", history: "", refusals: "", ties: true });
  const [done, setDone] = useState(false);
  const set = (k: string, v: unknown) => setF((p) => ({ ...p, [k]: v }));
  function submit(e: React.FormEvent) {
    e.preventDefault();
    setDone(true);
    send(t("assessNow"), {
      destination: f.destination, days: Number(f.days), travellers: Number(f.travellers),
      profile: {
        employment_status: f.employment_status,
        funds_available_minor: f.funds ? Math.round(Number(f.funds) * 100) : null,
        travel_history: codes(f.history).map((country) => ({ country })),
        prior_refusals: codes(f.refusals).map((country) => ({ country })),
        ties_to_pakistan: f.ties ? { family: true } : null,
      },
    });
  }
  if (done) return null;
  return (
    <Card>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        <h3 className="text-lg font-semibold sm:col-span-2">{t("profileTitle")}</h3>
        <Field label={t("destination")}><Select value={f.destination} onChange={(e) => set("destination", e.target.value)}>{DESTS.map((d) => <option key={d} value={d}>{d}</option>)}</Select></Field>
        <Field label={t("days")}><Input type="number" min={1} max={180} value={f.days} onChange={(e) => set("days", e.target.value)} /></Field>
        <Field label={t("employment")}><Select value={f.employment_status} onChange={(e) => set("employment_status", e.target.value)}>{EMP.map((x) => <option key={x} value={x}>{t(`emp_${x}`)}</option>)}</Select></Field>
        <Field label={t("funds")}><Input inputMode="numeric" value={f.funds} onChange={(e) => set("funds", e.target.value.replace(/[^\d]/g, ""))} placeholder="1500000" /></Field>
        <Field label={t("travelHistory")}><Input value={f.history} onChange={(e) => set("history", e.target.value)} placeholder="AE, TR" className="latin" /></Field>
        <Field label={t("refusals")}><Input value={f.refusals} onChange={(e) => set("refusals", e.target.value)} className="latin" /></Field>
        <label className="flex items-center gap-2 sm:col-span-2"><input type="checkbox" className="size-5" checked={f.ties} onChange={(e) => set("ties", e.target.checked)} />{t("ties")}</label>
        <Button type="submit" className="sm:col-span-2">{t("assessNow")}</Button>
      </form>
    </Card>
  );
}

// ------------------------------------------------------------------ scam
export function ScamResult({ r }: { r: CardData }) {
  const t = useTranslations("cards");
  const locale = useLocale();
  const tone = r.risk === "high" ? "bad" : r.risk === "medium" ? "warn" : "good";
  return (
    <Card className="space-y-3">
      <div className="flex items-center gap-2">
        <ShieldAlert aria-hidden className={cn("size-6", tone === "bad" ? "text-bad" : tone === "warn" ? "text-warn" : "text-good")} />
        <h3 className="text-lg font-semibold">{t("risk")}:</h3>
        <Badge tone={tone} className="text-base">{t(`risk_${r.risk}` as "risk_high")}</Badge>
      </div>
      {r.red_flags.length > 0 && (
        <div className="space-y-2">
          <h4 className="font-medium">{t("redFlags")}</h4>
          {r.red_flags.map((f: any, i: number) => (
            <div key={i} className="rounded-xl bg-bad-soft/60 p-3">
              <p>{L(locale, f.en, f.ur)}</p>
              {f.evidence && <p className="latin mt-1 text-sm text-ink-2">“{f.evidence}”</p>}
            </div>
          ))}
        </div>
      )}
      {r.licence && <p>{r.licence.found ? t("licenceFound", { n: r.licence.number, status: r.licence.status }) : t("licenceNotFound", { n: r.licence.number })}</p>}
      {r.official_facts.length > 0 && (
        <div className="space-y-2">
          <h4 className="font-medium">{t("officialFacts")}</h4>
          {r.official_facts.map((f: any, i: number) => (
            <div key={i} className="space-y-1">
              <p className={f.excerpt ? "latin text-[0.95em]" : ""}>{f.excerpt ? `“${f.en}”` : L(locale, f.en, f.ur)}</p>
              <Citation c={f.citation} />
            </div>
          ))}
        </div>
      )}
      <div className="space-y-1">
        <h4 className="font-medium">{t("howToVerify")}</h4>
        <ol className="list-decimal space-y-1 ps-6">{r.verification_steps.map((s: any, i: number) => <li key={i}>{L(locale, s.en, s.ur)}</li>)}</ol>
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ umrah
function UmrahForm({ c, send }: { c: CardData; send: SendFn }) {
  const t = useTranslations("cards");
  const [f, setF] = useState({ travellers: c.travellers || 2, start: "", nights_makkah: 7, nights_madinah: 5, origin: "LHE" });
  const set = (k: string, v: unknown) => setF((p) => ({ ...p, [k]: v }));
  return (
    <Card>
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); send(t("showOptions"), { action: "umrah_options", ...f }); }}>
        <h3 className="text-lg font-semibold sm:col-span-2">{t("umrahForm")}</h3>
        <Field label={t("travellers")}><Input type="number" min={1} max={20} value={f.travellers} onChange={(e) => set("travellers", Number(e.target.value))} /></Field>
        <Field label={t("start")}><Input type="date" required value={f.start} onChange={(e) => set("start", e.target.value)} /></Field>
        <Field label={t("nightsMakkah")}><Input type="number" min={1} max={30} value={f.nights_makkah} onChange={(e) => set("nights_makkah", Number(e.target.value))} /></Field>
        <Field label={t("nightsMadinah")}><Input type="number" min={0} max={30} value={f.nights_madinah} onChange={(e) => set("nights_madinah", Number(e.target.value))} /></Field>
        <Field label={t("origin")}><Select value={f.origin} onChange={(e) => set("origin", e.target.value)}>{["LHE", "KHI", "ISB", "MUX", "SKT", "PEW"].map((a) => <option key={a}>{a}</option>)}</Select></Field>
        <Button type="submit" className="self-end">{t("showOptions")}</Button>
      </form>
    </Card>
  );
}

function UmrahOptions({ c, send }: { c: CardData; send: SendFn }) {
  const t = useTranslations("cards");
  const locale = useLocale();
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {c.options.map((o: any) => (
        <Card key={o.code} className="flex flex-col gap-2">
          <h3 className="font-semibold">{L(locale, o.label_en, o.label_ur)}</h3>
          <p className="tabular latin text-xl font-semibold">{money(o.total_minor, "PKR", locale)}</p>
          <p className="text-sm text-ink-2">{t("distance", { m: o.makkah_distance_m })}</p>
          <ul className="space-y-1 text-sm">
            {o.lines.map((li: any, i: number) => (
              <li key={i} className="flex justify-between gap-2"><span className="latin">{li.name}{li.quantity > 1 ? ` × ${li.quantity}` : ""}</span><span className="tabular latin shrink-0">{money(li.amount_minor, li.currency, locale)}</span></li>
            ))}
          </ul>
          <p className="text-sm text-ink-2">{t("partner")}: <span className="latin">{o.partner_name}</span> · {t("licence")} <span className="latin">{o.partner_licence}</span></p>
          <Button className="mt-auto" onClick={() => send(L(locale, o.label_en, o.label_ur), { action: "select_umrah_option", option: o })}>{t("select")}</Button>
        </Card>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ flights / hotels
function FlightOptions({ c, send }: { c: CardData; send: SendFn }) {
  const t = useTranslations("cards");
  const tc = useTranslations("common");
  const locale = useLocale();
  return (
    <div className="space-y-2">
      <h3 className="text-lg font-semibold">{t("flights")} {c.offers[0]?.provider === "sandbox" && <Badge tone="warn">{tc("sandbox")}</Badge>}</h3>
      {c.offers.map((o: any) => (
        <Card key={o.offer_id} className="flex flex-wrap items-center gap-3">
          <div className="min-w-48 flex-1">
            <p className="font-medium latin">{o.airline} · {o.flight_numbers.join(", ")}</p>
            <p className="text-sm text-ink-2"><span className="latin">{o.origin} → {o.destination}</span> · {dateTime(o.depart_at, locale)} · {t("stops", { n: o.stops })}</p>
            <p className="text-sm text-ink-2">{t("baggage")}: <span className="latin">{o.baggage}</span> · {o.refundable ? t("refundable") : t("nonRefundable")}</p>
            <p className="text-sm text-ink-2">{L(locale, o.fare_rules_en, o.fare_rules_ur)}</p>
          </div>
          <div className="text-end">
            <p className="tabular latin text-lg font-semibold">{money(o.fare_minor + o.taxes_minor, o.currency, locale)}</p>
            <p className="tabular latin text-sm text-ink-2">{t("fare")} {money(o.fare_minor, o.currency, locale)} + {t("taxes")} {money(o.taxes_minor, o.currency, locale)}</p>
            <Button size="sm" className="mt-1" onClick={() => send(`${o.airline} ${o.flight_numbers.join(",")}`, { action: "select_offer", kind: "flight", offer: o })}>{t("select")}</Button>
          </div>
        </Card>
      ))}
    </div>
  );
}

function HotelOptions({ c, send }: { c: CardData; send: SendFn }) {
  const t = useTranslations("cards");
  const tc = useTranslations("common");
  const locale = useLocale();
  return (
    <div className="space-y-2">
      <h3 className="text-lg font-semibold">{t("hotels")} {c.offers[0]?.provider === "sandbox" && <Badge tone="warn">{tc("sandbox")}</Badge>}</h3>
      {c.offers.map((o: any) => (
        <Card key={o.offer_id} className="flex flex-wrap items-center gap-3">
          <div className="min-w-48 flex-1">
            <p className="font-medium latin">{o.name}</p>
            <p className="text-sm text-ink-2"><span className="latin">{o.room} · {o.board}</span> · {t("nights", { n: o.nights })}</p>
            <p className="text-sm"><Info aria-hidden className="me-1 inline size-4" />{t("cancellation")}: {L(locale, o.cancellation_en, o.cancellation_ur)}</p>
          </div>
          <div className="text-end">
            <p className="tabular latin text-lg font-semibold">{money(o.total_minor, o.currency, locale)}</p>
            <Button size="sm" className="mt-1" onClick={() => send(o.name, { action: "select_offer", kind: "hotel", offer: o })}>{t("select")}</Button>
          </div>
        </Card>
      ))}
    </div>
  );
}

export function BookingForm({ c, send, mode = "both" }: { c: CardData; send: SendFn; mode?: "both" | "flights" | "hotels" }) {
  const t = useTranslations("cards");
  const [fl, setFl] = useState({ origin: "LHE", destination: "JED", depart_date: c.today || "", return_date: "", adults: 1 });
  const [ho, setHo] = useState({ city: "Istanbul", check_in: c.today || "", check_out: "", guests: 2 });
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {mode !== "hotels" && (
        <Card>
          <form className="grid grid-cols-2 gap-3" onSubmit={(e) => { e.preventDefault(); send(t("searchFlights"), { action: "search_flights", ...fl, return_date: fl.return_date || null }); }}>
            <h3 className="col-span-2 font-semibold">{t("searchFlights")}</h3>
            <Field label={t("from")}><Input className="latin uppercase" maxLength={3} value={fl.origin} onChange={(e) => setFl({ ...fl, origin: e.target.value.toUpperCase() })} /></Field>
            <Field label={t("to")}><Input className="latin uppercase" maxLength={3} value={fl.destination} onChange={(e) => setFl({ ...fl, destination: e.target.value.toUpperCase() })} /></Field>
            <Field label={t("depart")}><Input type="date" required value={fl.depart_date} onChange={(e) => setFl({ ...fl, depart_date: e.target.value })} /></Field>
            <Field label={t("return")}><Input type="date" value={fl.return_date} onChange={(e) => setFl({ ...fl, return_date: e.target.value })} /></Field>
            <Field label={t("adults")}><Input type="number" min={1} max={9} value={fl.adults} onChange={(e) => setFl({ ...fl, adults: Number(e.target.value) })} /></Field>
            <Button type="submit" className="self-end">{t("searchFlights")}</Button>
          </form>
        </Card>
      )}
      {mode !== "flights" && (
        <Card>
          <form className="grid grid-cols-2 gap-3" onSubmit={(e) => { e.preventDefault(); send(t("searchHotels"), { action: "search_hotels", ...ho }); }}>
            <h3 className="col-span-2 font-semibold">{t("searchHotels")}</h3>
            <Field label={t("city")}><Input className="latin" value={ho.city} onChange={(e) => setHo({ ...ho, city: e.target.value })} /></Field>
            <Field label={t("guests")}><Input type="number" min={1} max={12} value={ho.guests} onChange={(e) => setHo({ ...ho, guests: Number(e.target.value) })} /></Field>
            <Field label={t("checkIn")}><Input type="date" required value={ho.check_in} onChange={(e) => setHo({ ...ho, check_in: e.target.value })} /></Field>
            <Field label={t("checkOut")}><Input type="date" required value={ho.check_out} onChange={(e) => setHo({ ...ho, check_out: e.target.value })} /></Field>
            <Button type="submit" className="col-span-2">{t("searchHotels")}</Button>
          </form>
        </Card>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ confirm action
export function ConfirmAction({ a, send, onDone }: { a: CardData; send?: SendFn; onDone?: () => void }) {
  const t = useTranslations("cards");
  const locale = useLocale();
  const { token } = useAuth();
  const [ticks, setTicks] = useState<Record<string, boolean>>({});
  const [state, setState] = useState<string>(a.status);
  const [err, setErr] = useState<string | null>(null);
  const decls: any[] = a.declarations || [];
  const allTicked = decls.every((d) => ticks[d.code]);
  const declarations = decls.map((d) => ({ code: d.code, accepted: Boolean(ticks[d.code]) }));
  async function confirm() {
    setErr(null);
    if (send) {
      send("", undefined, { confirmed: true, declarations });
      setState("awaiting_ops");
      return;
    }
    try {
      await api(`/actions/${a.action_id}/confirm`, { token, body: { declarations } });
      setState("awaiting_ops");
      onDone?.();
    } catch (e: any) {
      setErr(e.message);
    }
  }
  if (state !== "awaiting_user") {
    return <Notice tone="good">{state === "awaiting_ops" ? t("awaitingOps") : `${t("confirmed")} · ${L(locale, a.summary_en, a.summary_ur)}`}</Notice>;
  }
  return (
    <Card className="space-y-3 border-2 border-brand">
      <h3 className="text-lg font-semibold">{t("confirmTitle")}</h3>
      <p className="font-medium">{L(locale, a.summary_en, a.summary_ur)}</p>
      {decls.length > 0 && <p className="text-ink-2">{t("confirmDeclarations")}</p>}
      {decls.map((d) => (
        <label key={d.code} className="flex items-start gap-3 rounded-xl bg-surface-2 p-3">
          <input type="checkbox" className="mt-1.5 size-5 shrink-0" checked={Boolean(ticks[d.code])} onChange={(e) => setTicks({ ...ticks, [d.code]: e.target.checked })} />
          <span>{L(locale, d.en, d.ur)}</span>
        </label>
      ))}
      {err && <Notice tone="bad">{err}</Notice>}
      <div className="flex flex-wrap gap-2">
        <Button size="lg" disabled={!allTicked} onClick={confirm}>{t("confirmYes")}</Button>
        {send && <Button size="lg" variant="secondary" onClick={() => { send("", undefined, { confirmed: false }); setState("cancelled"); }}>{t("confirmNo")}</Button>}
      </div>
    </Card>
  );
}
