"use client";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Badge, Card, Notice } from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime } from "@/lib/format";

export function CasesList() {
  const t = useTranslations();
  const locale = useLocale();
  const { token, ready } = useAuth();
  const [cases, setCases] = useState<any[] | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    if (!token) return;
    api<any[]>("/cases", { token }).then(setCases).catch(() => setErr(true));
  }, [token]);
  if (!ready) return <p>{t("common.loading")}</p>;
  if (!token) return <Notice tone="brand"><Link href="/login" className="underline">{t("common.signInToContinue")}</Link></Notice>;
  if (err) return <Notice tone="bad">{t("common.error")}</Notice>;
  if (!cases) return <p>{t("common.loading")}</p>;
  if (cases.length === 0) return <p className="text-ink-2">{t("cases.empty")} <Link href="/chat" className="text-brand underline">{t("nav.chat")}</Link></p>;
  return (
    <ul className="space-y-2">
      {cases.map((c) => (
        <li key={c.id}>
          <Link href={`/cases/${c.id}`}>
            <Card className="flex flex-wrap items-center gap-3 hover:border-brand">
              <span className="font-medium">{c.service_type.replace("_", " ")} {c.destination_country ? `· ${c.destination_country}` : ""}</span>
              <Badge tone="brand">{t(`status.${c.status}` as "status.quoted")}</Badge>
              <span className="ms-auto text-sm text-ink-2">{dateTime(c.updated_at || c.created_at, locale)}</span>
            </Card>
          </Link>
        </li>
      ))}
    </ul>
  );
}
