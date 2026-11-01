"use client";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { Button, Card, Field, Input, Notice } from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function AccountView() {
  const t = useTranslations("account");
  const tc = useTranslations("common");
  const locale = useLocale();
  const { token, ready } = useAuth();
  const [me, setMe] = useState<any>(null);
  const [travellers, setTravellers] = useState<any[]>([]);
  const [f, setF] = useState({ full_name_as_passport: "", date_of_birth: "", passport_number: "", passport_expiry: "", cnic: "", relationship_to_owner: "" });
  const [msg, setMsg] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  const load = useCallback(() => {
    if (!token) return;
    api("/me", { token }).then(setMe).catch(() => {});
    api<any[]>("/travellers", { token }).then(setTravellers).catch(() => {});
  }, [token]);
  useEffect(load, [load]);
  if (!ready) return <p>{tc("loading")}</p>;
  if (!token) return <Notice tone="brand"><Link href="/login" className="underline">{tc("signInToContinue")}</Link></Notice>;

  async function add(e: React.FormEvent) {
    e.preventDefault();
    const body = Object.fromEntries(Object.entries(f).filter(([, v]) => v));
    try {
      await api("/travellers", { token, body });
      setF({ full_name_as_passport: "", date_of_birth: "", passport_number: "", passport_expiry: "", cnic: "", relationship_to_owner: "" });
      load();
    } catch (e: any) {
      setMsg({ tone: "bad", text: e.message });
    }
  }
  async function exportData() {
    const data = await api("/me/export", { token });
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "rahbar-my-data.json";
    a.click();
    URL.revokeObjectURL(url);
  }
  async function del() {
    if (!window.confirm(t("deleteConfirm"))) return;
    try {
      const r = await api<any>("/me", { token, method: "DELETE" });
      setMsg({ tone: "good", text: `✓ ${r.deleted_documents}` });
    } catch (e: any) {
      setMsg({ tone: "bad", text: e.message });
    }
  }
  return (
    <div className="space-y-5">
      <h1 className="text-3xl font-semibold">{t("title")}</h1>
      {me && <p className="text-ink-2">{me.full_name || ""}</p>}
      <Card className="space-y-3">
        <h2 className="text-lg font-semibold">{t("travellers")}</h2>
        <ul className="space-y-1">
          {travellers.map((tr) => (
            <li key={tr.id} className="latin">{tr.full_name_as_passport} {tr.relationship_to_owner ? `(${tr.relationship_to_owner})` : ""} · {tr.passport_number_masked ?? "—"}</li>
          ))}
        </ul>
        <p className="text-sm text-ink-2">{t("encrypted")}</p>
        <form onSubmit={add} className="grid gap-3 sm:grid-cols-2">
          <h3 className="font-medium sm:col-span-2">{t("addTraveller")}</h3>
          <Field label={t("name")}><Input required className="latin uppercase" value={f.full_name_as_passport} onChange={(e) => setF({ ...f, full_name_as_passport: e.target.value })} /></Field>
          <Field label={t("relationship")}><Input value={f.relationship_to_owner} onChange={(e) => setF({ ...f, relationship_to_owner: e.target.value })} /></Field>
          <Field label={t("dob")}><Input type="date" value={f.date_of_birth} onChange={(e) => setF({ ...f, date_of_birth: e.target.value })} /></Field>
          <Field label={t("passport")}><Input className="latin uppercase" autoComplete="off" value={f.passport_number} onChange={(e) => setF({ ...f, passport_number: e.target.value })} /></Field>
          <Field label={t("passportExpiry")}><Input type="date" value={f.passport_expiry} onChange={(e) => setF({ ...f, passport_expiry: e.target.value })} /></Field>
          <Field label={t("cnic")}><Input className="latin" inputMode="numeric" autoComplete="off" placeholder="35202-1234567-1" value={f.cnic} onChange={(e) => setF({ ...f, cnic: e.target.value })} /></Field>
          <Button type="submit" className="sm:col-span-2">{tc("save")}</Button>
        </form>
      </Card>
      <Card className="space-y-3">
        <label className="flex items-center gap-2">
          <input type="checkbox" className="size-5" checked={Boolean(me?.keep_documents)} onChange={(e) => api("/me", { token, method: "PATCH", body: { keep_documents: e.target.checked } }).then(load)} />
          {t("keepDocs")}
        </label>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={exportData}>{t("export")}</Button>
          <Button variant="danger" onClick={del}>{t("delete")}</Button>
        </div>
        {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
      </Card>
      <p className="sr-only">{locale}</p>
    </div>
  );
}
