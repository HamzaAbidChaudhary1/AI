"use client";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { Notice } from "@/components/ui";
import { Link, usePathname } from "@/i18n/navigation";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/format";

export function OpsShell({ children, error }: { children: ReactNode; error?: { status: number; message: string } | null }) {
  const t = useTranslations("ops");
  const tc = useTranslations("common");
  const pathname = usePathname();
  const { token, ready } = useAuth();
  const tabs = [["/ops", t("queue")], ["/ops/sources", t("sources")], ["/ops/partners", t("partners")], ["/ops/usage", t("usage")]] as const;
  return (
    <div className="space-y-4" lang="en" dir="ltr">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="me-4 text-2xl font-semibold">{t("title")}</h1>
        {tabs.map(([href, label]) => (
          <Link key={href} href={href} className={cn("rounded-lg px-3 py-1.5 hover:bg-surface-2", (pathname === href || (href !== "/ops" && pathname.startsWith(href))) && "bg-surface-2 font-medium")}>{label}</Link>
        ))}
      </div>
      {ready && !token ? <Notice tone="brand"><Link href="/login" className="underline">{tc("signInToContinue")}</Link></Notice>
        : error && (error.status === 403 || error.status === 401) ? <Notice tone="bad">{t("notStaff")} ({error.message})</Notice>
        : error ? <Notice tone="bad">{error.message}</Notice>
        : children}
    </div>
  );
}
