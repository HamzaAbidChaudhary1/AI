"use client";
import { useTranslations } from "next-intl";
import { use } from "react";
import { OpsShell } from "@/components/ops/OpsShell";
import { useOps } from "@/components/ops/useOps";
import { Badge, Button, Card } from "@/components/ui";
import { diffLines } from "@/lib/diff";
import { cn, dateTime } from "@/lib/format";

const show = (v: any) => (v == null ? "—" : typeof v === "object" ? v.text ?? JSON.stringify(v) : String(v));

export default function OpsSource({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("ops");
  const { data: d, error, call } = useOps<any>(`/ops/sources/${id}`);
  const diff = d?.latest && d?.previous ? diffLines(d.previous.content_markdown, d.latest.content_markdown) : null;
  return (
    <OpsShell error={error}>
      {d && (
        <>
          <div className="space-y-1">
            <h2 className="text-xl font-semibold">{d.source.title}</h2>
            <a href={d.source.url} className="text-sm text-brand underline" target="_blank" rel="noopener noreferrer">{d.source.url}</a>
            {d.latest && <p className="text-sm text-ink-2">{t("lastSeen")}: {dateTime(d.latest.last_seen_at, "en")} · {t("provider")} {d.latest.provider} {d.latest.provider === "fixture" && <Badge tone="warn">{t("testData")}</Badge>}</p>}
          </div>
          {d.reviews.length > 0 && (
            <Card className="space-y-2 border-warn">
              {d.reviews.map((r: any) => (
                <p key={r.id}><Badge tone="warn">{r.payload.field}</Badge> {show(r.payload.old)} → <strong>{show(r.payload.new)}</strong></p>
              ))}
            </Card>
          )}
          <Card>
            <h3 className="mb-2 font-semibold">{t("records")}</h3>
            <table className="w-full text-sm">
              <tbody>
                {d.policy_records.map((r: any) => (
                  <tr key={r.id} className="border-t border-line">
                    <td className="p-1.5">{r.field}</td>
                    <td className="max-w-md p-1.5">{show(r.value)}</td>
                    <td className="p-1.5"><Badge tone={r.status === "verified" ? "good" : r.status === "disputed" ? "bad" : r.status === "stale" ? "neutral" : "warn"}>{r.status}</Badge></td>
                    <td className="p-1.5">
                      {(r.status === "auto" || r.status === "disputed") && <Button size="sm" onClick={() => call(`/ops/policy/${r.id}`, { decision: "verify" })}>{t("verify")}</Button>}{" "}
                      {r.status !== "disputed" && r.status !== "stale" && <Button size="sm" variant="secondary" onClick={() => call(`/ops/policy/${r.id}`, { decision: "dispute" })}>{t("dispute")}</Button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Card>
            <h3 className="mb-2 font-semibold">{t("diff")}</h3>
            {!diff ? <p className="text-ink-2">{t("noDiff")}</p> : (
              <pre className="max-h-[32rem] overflow-auto text-xs">
                {diff.map((l, i) => <div key={i} className={cn(l.kind === "add" && "bg-good-soft text-good", l.kind === "del" && "bg-bad-soft text-bad line-through")}>{l.kind === "add" ? "+ " : l.kind === "del" ? "- " : "  "}{l.text}</div>)}
              </pre>
            )}
          </Card>
        </>
      )}
    </OpsShell>
  );
}
