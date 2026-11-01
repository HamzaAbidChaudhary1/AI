import { getTranslations, setRequestLocale } from "next-intl/server";

export default async function PrivacyPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("legal");
  return (
    <article className="max-w-3xl space-y-4">
      <h1 className="text-3xl font-semibold">{t("privacy")}</h1>
      <p>{t("privacyBody")}</p>
    </article>
  );
}
