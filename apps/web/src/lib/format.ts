const MINOR = 100;

/** Money is stored as integer minor units; we always show the currency code (UI_I18N.md). */
export function money(amountMinor: number, currency: string, locale: string): string {
  const value = amountMinor / MINOR;
  const n = new Intl.NumberFormat(locale === "ur" ? "ur-PK" : "en-PK", {
    maximumFractionDigits: Number.isInteger(value) ? 0 : 2,
    minimumFractionDigits: Number.isInteger(value) ? 0 : 2,
  }).format(value);
  return `${currency} ${n}`;
}

/** All timestamps are UTC in the DB; display in Asia/Karachi. */
export function dateTime(iso: string | null | undefined, locale: string, withTime = true): string {
  if (!iso) return "";
  return new Intl.DateTimeFormat(locale === "ur" ? "ur-PK" : "en-GB", {
    timeZone: "Asia/Karachi",
    dateStyle: "medium",
    ...(withTime ? { timeStyle: "short" } : {}),
  }).format(new Date(iso));
}

export function cn(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}
