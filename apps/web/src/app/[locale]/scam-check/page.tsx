import { getTranslations, setRequestLocale } from "next-intl/server";
import { ScamForm } from "./ScamForm";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  return { title: (await getTranslations({ locale, namespace: "scam" }))("title") };
}

export default async function ScamPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("scam");
  return (
    <div className="max-w-3xl space-y-4">
      <h1 className="text-3xl font-semibold">{t("title")}</h1>
      <p className="text-lg text-ink-2">{t("intro")}</p>
      <ScamForm />
    </div>
  );
}
