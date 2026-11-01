import { getTranslations, setRequestLocale } from "next-intl/server";
import { CasesList } from "./CasesList";

export default async function CasesPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("cases");
  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-semibold">{t("title")}</h1>
      <CasesList />
    </div>
  );
}
