"use client";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { OpsShell } from "@/components/ops/OpsShell";
import { useOps } from "@/components/ops/useOps";
import { Badge, Button, Card, Field, Input, Notice, Select } from "@/components/ui";
import { money } from "@/lib/format";

export default function OpsPartners() {
  const t = useTranslations("ops");
  const partners = useOps<any[]>("/ops/partners");
  const inv = useOps<any[]>("/ops/inventory");
  const [f, setF] = useState({ partner_id: "", kind: "hotel_makkah", name: "", unit_amount_minor: "", per: "person_night", valid_from: "", valid_to: "", stars: "", distance: "" });
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <OpsShell error={partners.error}>
      <Card>
        <ul className="space-y-1">
          {partners.data?.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center gap-2">
              <strong>{p.name}</strong><Badge>{p.kind}</Badge><span className="text-sm text-ink-2">{t("licenceLine", { n: p.licence_number, authority: p.licence_authority, expiry: p.licence_expiry })}</span>
              {!p.active && <Badge tone="bad">{t("inactive")}</Badge>}<span className="text-sm">{t("itemsCount", { n: p.inventory })}</span>
            </li>
          ))}
        </ul>
      </Card>
      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[40rem] text-sm">
          <tbody>
            {inv.data?.map((i) => (
              <tr key={i.id} className="border-t border-line"><td className="p-2">{i.kind}</td><td className="p-2">{i.name}</td><td className="p-2">{money(i.unit_amount_minor, i.currency, "en")} / {i.per}</td><td className="p-2">{i.valid_from} → {i.valid_to}</td></tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card>
        <form className="grid gap-2 sm:grid-cols-3" onSubmit={(e) => {
          e.preventDefault();
          inv.call("/ops/inventory", { partner_id: f.partner_id, kind: f.kind, name: f.name, unit_amount_minor: Number(f.unit_amount_minor), per: f.per, valid_from: f.valid_from, valid_to: f.valid_to, currency: "PKR",
            details: { ...(f.stars ? { stars: Number(f.stars) } : {}), ...(f.distance ? { distance_to_haram_m: Number(f.distance) } : {}) } }).then(() => setMsg("✓")).catch((x) => setMsg(x.message));
        }}>
          <h3 className="font-semibold sm:col-span-3">{t("addInventory")}</h3>
          <Field label={t("partners")}><Select required value={f.partner_id} onChange={(e) => setF({ ...f, partner_id: e.target.value })}><option value="" />{partners.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>
          <Field label={t("kind")}><Select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>{["visa", "flight", "hotel_makkah", "hotel_madinah", "transport", "ziyarat", "insurance"].map((k) => <option key={k}>{k}</option>)}</Select></Field>
          <Field label={t("name")}><Input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label={t("price")}><Input required inputMode="numeric" value={f.unit_amount_minor} onChange={(e) => setF({ ...f, unit_amount_minor: e.target.value })} /></Field>
          <Field label={t("per")}><Select value={f.per} onChange={(e) => setF({ ...f, per: e.target.value })}>{["person", "person_night", "room_night", "booking"].map((k) => <option key={k}>{k}</option>)}</Select></Field>
          <Field label={t("stars")}><Input inputMode="numeric" value={f.stars} onChange={(e) => setF({ ...f, stars: e.target.value })} /></Field>
          <Field label={t("distance")}><Input inputMode="numeric" value={f.distance} onChange={(e) => setF({ ...f, distance: e.target.value })} /></Field>
          <Field label={t("validFrom")}><Input required type="date" value={f.valid_from} onChange={(e) => setF({ ...f, valid_from: e.target.value })} /></Field>
          <Field label={t("validTo")}><Input required type="date" value={f.valid_to} onChange={(e) => setF({ ...f, valid_to: e.target.value })} /></Field>
          <Button type="submit" className="sm:col-span-3">{t("addInventory")}</Button>
        </form>
        {msg && <Notice tone="brand">{msg}</Notice>}
      </Card>
    </OpsShell>
  );
}
