import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["en", "ur"],
  defaultLocale: "en",
  localeCookie: { name: "NEXT_LOCALE", maxAge: 60 * 60 * 24 * 365 },
});

export type Locale = (typeof routing.locales)[number];
export const isRtl = (l: string) => l === "ur";
