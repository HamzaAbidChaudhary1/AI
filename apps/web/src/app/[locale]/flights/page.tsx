import { getTranslations, setRequestLocale } from "next-intl/server";
import { Chat } from "@/components/chat/Chat";

export default async function FlightsPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("booking");
  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-semibold">{t("flightsTitle")}</h1>
      <p className="text-lg text-ink-2">{t("intro")}</p>
      <Chat hideIntro initialMessage="flights" initialPayload={{ action: "booking_form" }} />
    </div>
  );
}
