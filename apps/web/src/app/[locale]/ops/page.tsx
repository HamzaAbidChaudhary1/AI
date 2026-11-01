"use client";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { OpsShell } from "@/components/ops/OpsShell";
import { useOps } from "@/components/ops/useOps";
import { Badge, Card, Select } from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { dateTime } from "@/lib/format";

const STATUSES = ["", "quoted", "accepted", "collecting_documents", "documents_review", "pack_ready", "awaiting_user_confirmation", "submitted", "biometrics_scheduled", "in_process", "booked"];

export default function OpsQueue() {
  const t = useTranslations("ops");
  const [status, setStatus] = useState("");
  const [sla, setSla] = useState(false);
  const q = new URLSearchParams({ ...(status ? { status } : {}), ...(sla ? { sla_breach: "true" } : {}) }).toString();
  const { data, error } = useOps<any[]>(`/ops/cases${q ? `?${q}` : ""}`);
  const tasks = useOps<any[]>("/ops/tasks");
  return (
    <OpsShell error={error}>
      <div className="flex flex-wrap items-end gap-3">
        <label className="space-y-1"><span className="text-sm text-ink-2">{t("status")}</span>
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="min-w-56">{STATUSES.map((s) => <option key={s} value={s}>{s || t("all")}</option>)}</Select>
        </label>
        <label className="flex items-center gap-2 pb-2"><input type="checkbox" className="size-5" checked={sla} onChange={(e) => setSla(e.target.checked)} />{t("sla")}</label>
        <span className="ms-auto text-sm text-ink-2">{t("tasks")}: {tasks.data?.length ?? "…"}</span>
      </div>
      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[44rem] text-sm">
          <thead className="bg-surface-2 text-ink-2"><tr><th className="p-2 text-start">{t("service")}</th><th className="p-2 text-start">{t("status")}</th><th className="p-2 text-start">{t("customer")}</th><th className="p-2 text-start">{t("tasks")}</th><th className="p-2 text-start">{t("updated")}</th></tr></thead>
          <tbody>
            {data?.map((c) => (
              <tr key={c.id} className="border-t border-line hover:bg-surface-2">
                <td className="p-2"><Link href={`/ops/cases/${c.id}`} className="text-brand underline">{c.service_type} {c.destination_country ?? ""}</Link></td>
                <td className="p-2"><Badge>{c.status}</Badge> {c.sla_breach && <Badge tone="bad">{t("sla")}</Badge>}</td>
                <td className="p-2">{c.customer ?? "—"}</td>
                <td className="p-2">{c.open_tasks > 0 ? <Badge tone="warn">{c.open_tasks}</Badge> : "—"}</td>
                <td className="p-2">{dateTime(c.updated_at || c.created_at, "en")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </OpsShell>
  );
}
