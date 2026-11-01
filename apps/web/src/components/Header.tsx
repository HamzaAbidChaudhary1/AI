"use client";
import { Menu, ShieldCheck, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Link, usePathname, useRouter } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/format";

export function Header() {
  const t = useTranslations("nav");
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  const { token, ready, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const other = locale === "en" ? "ur" : "en";

  async function switchLocale() {
    if (token) api("/me", { token, method: "PATCH", body: { preferred_locale: other } }).catch(() => {});
    router.replace(pathname, { locale: other });
  }

  const links = [
    { href: "/chat", label: t("chat") },
    { href: "/scam-check", label: t("scam") },
    { href: "/umrah", label: t("umrah") },
    { href: "/flights", label: t("flights") },
    { href: "/cases", label: t("cases") },
  ] as const;

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-bg/95 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-2">
        <Link href="/" className="flex items-center gap-2 text-lg font-semibold text-brand">
          <ShieldCheck aria-hidden className="size-6" />
          <span>{locale === "ur" ? "رہبر" : "Rahbar"}</span>
        </Link>
        <nav className="ms-4 hidden flex-1 items-center gap-1 md:flex" aria-label="main">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className={cn("rounded-lg px-3 py-2 text-[0.95em] hover:bg-surface-2", pathname.startsWith(l.href) && "bg-surface-2 font-medium")}>
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="ms-auto flex items-center gap-1">
          <button onClick={switchLocale} className="min-h-11 rounded-lg px-3 hover:bg-surface-2" lang={other} aria-label={other === "ur" ? "اردو میں دیکھیں" : "View in English"}>
            {t("language")}
          </button>
          {ready && (token ? (
            <>
              <Link href="/account" className="hidden min-h-11 items-center rounded-lg px-3 hover:bg-surface-2 sm:inline-flex">{t("account")}</Link>
              <button onClick={() => signOut()} className="hidden min-h-11 rounded-lg px-3 hover:bg-surface-2 sm:inline-block">{t("logout")}</button>
            </>
          ) : (
            <Link href="/login" className="inline-flex min-h-11 items-center rounded-lg bg-brand px-3 text-brand-ink">{t("login")}</Link>
          ))}
          <button className="min-h-11 rounded-lg px-2 md:hidden" onClick={() => setOpen(!open)} aria-expanded={open} aria-label="menu">
            {open ? <X /> : <Menu />}
          </button>
        </div>
      </div>
      {open && (
        <nav className="border-t border-line px-4 pb-3 md:hidden" aria-label="mobile">
          {[...links, { href: "/hotels", label: t("hotels") }, { href: "/account", label: t("account") }].map((l) => (
            <Link key={l.href} href={l.href} onClick={() => setOpen(false)} className="block rounded-lg px-2 py-3 text-lg hover:bg-surface-2">{l.label}</Link>
          ))}
          {token && <button onClick={() => signOut()} className="block w-full rounded-lg px-2 py-3 text-start text-lg hover:bg-surface-2">{t("logout")}</button>}
        </nav>
      )}
    </header>
  );
}
