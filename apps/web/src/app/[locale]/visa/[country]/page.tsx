import { getTranslations, setRequestLocale } from "next-intl/server";
import { Citation } from "@/components/cards/Cards";
import { Card, Notice } from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { API_URL } from "@/lib/config";

type Fact = { field: string; value: any; fresh: boolean; status: string; citation: any };
const ORDER = ["gov_fee", "service_centre_fee", "processing_time", "max_stay", "validity", "biometrics_required", "interview_required", "insurance_required", "apply_from", "proof_of_funds", "photo_specs"];

async function load(country: string) {
  const r = await fetch(`${API_URL}/public/visa/${country}`, { next: { revalidate: 300 } });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error("api");
  return (await r.json()) as { name_en: string; name_ur: string; facts: Record<string, Fact> };
}

function show(v: any): string {
  if (v == null) return "";
  if (Array.isArray(v)) return v.join("; ");
  if (typeof v === "object") return v.text ?? JSON.stringify(v);
  return String(v);
}

export default async function VisaPage({ params }: { params: Promise<{ locale: string; country: string }> }) {
  const { locale, country } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("visa");
  const tc = await getTranslations("common");
  let data: Awaited<ReturnType<typeof load>> = null;
  let failed = false;
  try {
    data = await load(country.toUpperCase());
  } catch {
    failed = true;
  }
  if (failed) return <Notice tone="bad">{tc("error")}</Notice>;
  if (!data) return <Notice>{t("notCovered")}</Notice>;
  const name = locale === "ur" ? data.name_ur : data.name_en;
  const docs = data.facts.required_documents;
  return (
    <div className="space-y-5">
      <h1 className="text-3xl font-semibold">{t("title", { country: name })}</h1>
      <Notice tone="brand">{tc("noGuarantee")}</Notice>
      <Card>
        <h2 className="mb-3 text-xl font-semibold">{t("requirements")}</h2>
        <dl className="divide-y divide-line">
          {ORDER.filter((f) => data.facts[f]).map((f) => {
            const fact = data.facts[f]!;
            return (
              <div key={f} className="grid gap-1 py-3 sm:grid-cols-[14rem_1fr]">
                <dt className="font-medium">{t(`field_${f}` as "field_gov_fee")}</dt>
                <dd className="space-y-1">
                  <div className="latin">{show(fact.value)}{!fact.fresh && <span className="ms-2 text-sm text-warn">({tc("maybeOutdated")})</span>}</div>
                  <Citation c={fact.citation} />
                </dd>
              </div>
            );
          })}
        </dl>
      </Card>
      {docs && (
        <Card>
          <h2 className="mb-3 text-xl font-semibold">{t("documents")}</h2>
          <ul className="latin list-disc space-y-1 ps-6">{(docs.value as string[]).map((d, i) => <li key={i}>{d}</li>)}</ul>
          <div className="mt-3"><Citation c={docs.citation} /></div>
        </Card>
      )}
      <div className="flex flex-wrap gap-3">
        <Link href={{ pathname: "/chat", query: { q: `${data.name_en} visit visa — my chances?` } }} className="inline-flex min-h-12 items-center rounded-xl bg-brand px-5 text-brand-ink">{t("ask")}</Link>
      </div>
    </div>
  );
}
