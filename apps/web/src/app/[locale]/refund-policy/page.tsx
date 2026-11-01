import { getTranslations, setRequestLocale } from "next-intl/server";
import { Card, Notice } from "@/components/ui";
import { API_URL } from "@/lib/config";

export default async function RefundPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations();
  let policies: any[] | null = null;
  try {
    const r = await fetch(`${API_URL}/public/refund-policies`, { next: { revalidate: 600 } });
    if (r.ok) policies = await r.json();
  } catch {
    policies = null;
  }
  return (
    <article className="max-w-3xl space-y-4">
      <h1 className="text-3xl font-semibold">{t("legal.refunds")}</h1>
      {!policies && <Notice tone="bad">{t("common.error")}</Notice>}
      {policies?.map((p) => (
        <Card key={p.service_type}>
          <h2 className="mb-1 font-semibold">{p.service_type.replace("_", " ")}</h2>
          <p>{locale === "ur" ? p.text_ur : p.text_en}</p>
        </Card>
      ))}
    </article>
  );
}
