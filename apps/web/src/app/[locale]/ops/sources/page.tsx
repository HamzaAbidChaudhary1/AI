"use client";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { OpsShell } from "@/components/ops/OpsShell";
import { useOps } from "@/components/ops/useOps";
import { Badge, Button, Card, Field, Input, Notice, Select } from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { dateTime } from "@/lib/format";

export default function OpsSources() {
  const t = useTranslations("ops");
  const { data, error, call } = useOps<any[]>("/ops/sources");
  const [f, setF] = useState({ url: "", title: "", country: "", topic: "visit_visa", visa_type: "", crawl_method: "firecrawl" });
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <OpsShell error={error}>
      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[48rem] text-sm">
          <thead className="bg-surface-2 text-ink-2"><tr><th className="p-2 text-start">{t("url")}</th><th className="p-2 text-start">{t("country")}</th><th className="p-2 text-start">{t("topic")}</th><th className="p-2 text-start">{t("lastSeen")}</th><th className="p-2 text-start">{t("status")}</th><th className="p-2" /></tr></thead>
          <tbody>
            {data?.map((s) => (
              <tr key={s.id} className="border-t border-line">
                <td className="max-w-80 truncate p-2"><Link href={`/ops/sources/${s.id}`} className="text-brand underline">{s.title || s.url}</Link></td>
                <td className="p-2">{s.country ?? "—"}</td>
                <td className="p-2">{s.topic}</td>
                <td className="p-2">{s.last_seen_at ? dateTime(s.last_seen_at, "en") : "—"}</td>
                <td className="p-2">{s.last_crawl_status && <Badge tone={s.last_crawl_status === "ok" ? "good" : "bad"}>{s.last_crawl_status.slice(0, 30)}</Badge>} {s.open_reviews > 0 && <Badge tone="warn">{s.open_reviews} {t("pendingReview")}</Badge>}</td>
                <td className="p-2"><Button size="sm" variant="secondary" onClick={() => call(`/ops/sources/${s.id}/crawl`)}>{t("crawlNow")}</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card>
        <form className="grid gap-2 sm:grid-cols-3" onSubmit={(e) => { e.preventDefault(); call("/ops/sources", { ...f, country: f.country || null, visa_type: f.visa_type || null }).then(() => setMsg("✓")).catch((x) => setMsg(x.message)); }}>
          <h3 className="font-semibold sm:col-span-3">{t("addSource")}</h3>
          <Field label={t("url")}><Input required type="url" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} /></Field>
          <Field label={t("name")}><Input required value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          <Field label={t("country")}><Input maxLength={2} value={f.country} onChange={(e) => setF({ ...f, country: e.target.value.toUpperCase() })} /></Field>
          <Field label={t("topic")}><Select value={f.topic} onChange={(e) => setF({ ...f, topic: e.target.value })}>{["visit_visa", "fees", "umrah", "biometrics", "scam_warning"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
          <Field label={t("visaType")}><Input value={f.visa_type} onChange={(e) => setF({ ...f, visa_type: e.target.value })} /></Field>
          <Field label={t("crawlMethod")}><Select value={f.crawl_method} onChange={(e) => setF({ ...f, crawl_method: e.target.value })}><option>firecrawl</option><option>apify</option></Select></Field>
          <Button type="submit" className="sm:col-span-3">{t("addSource")}</Button>
        </form>
        {msg && <Notice tone="brand">{msg}</Notice>}
      </Card>
    </OpsShell>
  );
}
