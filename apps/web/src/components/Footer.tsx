import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

export function Footer() {
  const t = useTranslations();
  return (
    <footer className="border-t border-line py-6 text-sm text-ink-2">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-4 gap-y-2 px-4">
        <span>{t("common.noGuarantee")}</span>
        <span className="ms-auto flex flex-wrap gap-3">
          <Link href="/how-we-are-different" className="underline">{t("nav.different")}</Link>
          <Link href="/refund-policy" className="underline">{t("legal.refunds")}</Link>
          <Link href="/terms" className="underline">{t("legal.terms")}</Link>
          <Link href="/privacy" className="underline">{t("legal.privacy")}</Link>
        </span>
      </div>
    </footer>
  );
}
