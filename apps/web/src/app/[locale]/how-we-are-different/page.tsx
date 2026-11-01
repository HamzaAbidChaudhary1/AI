import { getTranslations, setRequestLocale } from "next-intl/server";

export default async function DifferentPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations();
  return (
    <article className="max-w-3xl space-y-4">
      <h1 className="text-3xl font-semibold">{t("different.title")}</h1>
      <p className="text-lg">{t("different.body")}</p>
      <ol className="list-decimal space-y-2 ps-6">
        {(["t1", "t2", "t3", "t4", "t5"] as const).map((k) => <li key={k}>{t(`home.${k}`)}</li>)}
      </ol>
      <p className="font-medium">{t("common.noGuarantee")}</p>
    </article>
  );
}
