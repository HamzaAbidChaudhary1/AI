import { ArrowRight, BadgeCheck, FileSearch, Hotel, Landmark, ShieldAlert } from "lucide-react";
import { useTranslations } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import { use } from "react";
import { Card } from "@/components/ui";
import { Link } from "@/i18n/navigation";

const DESTS: [string, string, string][] = [["GB", "United Kingdom", "برطانیہ"], ["DE", "Schengen (Germany)", "(Schengen) جرمنی"], ["TR", "Türkiye", "ترکیہ"], ["AE", "UAE", "یو اے ای"], ["MY", "Malaysia", "ملائیشیا"], ["SA", "Saudi Arabia", "سعودی عرب"]];

export default function Home({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = use(params);
  setRequestLocale(locale);
  const t = useTranslations("home");
  const services = [
    { icon: BadgeCheck, t: t("s1t"), d: t("s1d"), href: "/chat" },
    { icon: Landmark, t: t("s2t"), d: t("s2d"), href: "/visa/GB" },
    { icon: FileSearch, t: t("s3t"), d: t("s3d"), href: "/umrah" },
    { icon: Hotel, t: t("s4t"), d: t("s4d"), href: "/flights" },
    { icon: ShieldAlert, t: t("s5t"), d: t("s5d"), href: "/scam-check" },
  ] as const;
  return (
    <div className="space-y-12">
      <section className="space-y-5 pt-6">
        <h1 className="text-4xl font-semibold leading-tight text-brand sm:text-5xl">{t("hero")}</h1>
        <p className="max-w-2xl text-lg text-ink-2">{t("subhero")}</p>
        <div className="flex flex-wrap gap-3">
          <Link href="/chat" className="inline-flex min-h-13 items-center gap-2 rounded-xl bg-brand px-6 text-lg text-brand-ink">{t("ctaChat")}<ArrowRight aria-hidden className="size-5 rtl:-scale-x-100" /></Link>
          <Link href="/scam-check" className="inline-flex min-h-13 items-center gap-2 rounded-xl border-2 border-brand px-6 text-lg text-brand">{t("ctaScam")}</Link>
        </div>
      </section>
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">{t("servicesTitle")}</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {services.map((s) => (
            <Link key={s.t} href={s.href}>
              <Card className="h-full space-y-2 transition hover:border-brand">
                <s.icon aria-hidden className="size-7 text-brand" />
                <h3 className="text-lg font-semibold">{s.t}</h3>
                <p className="text-ink-2">{s.d}</p>
              </Card>
            </Link>
          ))}
        </div>
      </section>
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">{t("transparencyTitle")}</h2>
        <ol className="grid gap-3 sm:grid-cols-2">
          {[t("t1"), t("t2"), t("t3"), t("t4"), t("t5")].map((x, i) => (
            <li key={i} className="flex gap-3 rounded-2xl bg-surface p-4">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-brand-soft font-semibold text-brand">{i + 1}</span>
              <span>{x}</span>
            </li>
          ))}
        </ol>
      </section>
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">{t("destinations")}</h2>
        <div className="flex flex-wrap gap-2">
          {DESTS.map(([c, en, ur]) => (
            <Link key={c} href={`/visa/${c}`} className="rounded-full border border-line bg-surface px-4 py-2 hover:border-brand">{locale === "ur" ? ur : en}</Link>
          ))}
        </div>
      </section>
    </div>
  );
}
