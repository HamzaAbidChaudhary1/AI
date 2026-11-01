import { setRequestLocale } from "next-intl/server";
import { CaseView } from "./CaseView";

export default async function CasePage({ params }: { params: Promise<{ locale: string; id: string }> }) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  return <CaseView id={id} />;
}
