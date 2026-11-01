"use client";
import { useTranslations } from "next-intl";
import { OpsShell } from "@/components/ops/OpsShell";
import { useOps } from "@/components/ops/useOps";
import { Card } from "@/components/ui";
import { Link } from "@/i18n/navigation";

export default function OpsUsage() {
  const t = useTranslations("ops");
  const { data, error } = useOps<any[]>("/ops/usage");
  return (
    <OpsShell error={error}>
      <h2 className="text-xl font-semibold">{t("usage")}</h2>
      <Card className="overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-ink-2"><tr><th className="p-2 text-start">{t("case")}</th><th className="p-2 text-start">{t("model")}</th><th className="p-2 text-end">{t("calls")}</th><th className="p-2 text-end">{t("inputTokens")}</th><th className="p-2 text-end">{t("outputTokens")}</th></tr></thead>
          <tbody>
            {data?.map((r, i) => (
              <tr key={i} className="border-t border-line">
                <td className="p-2">{r.case_id ? <Link href={`/ops/cases/${r.case_id}`} className="text-brand underline">{String(r.case_id).slice(0, 8)}</Link> : "—"}</td>
                <td className="p-2 font-mono">{r.model}</td><td className="p-2 text-end">{r.calls}</td><td className="p-2 text-end">{r.input_tokens}</td><td className="p-2 text-end">{r.output_tokens}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </OpsShell>
  );
}
