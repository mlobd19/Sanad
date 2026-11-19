import type { Lang } from "./i18n";

export function money(amount: number, lang: Lang): string {
  const n = new Intl.NumberFormat(lang === "ar" ? "ar-MR" : "fr-FR").format(amount);
  return lang === "ar" ? `${n} أوقية` : `${n} MRU`;
}

export function num(n: number, lang: Lang): string {
  return new Intl.NumberFormat(lang === "ar" ? "ar-MR" : "fr-FR").format(n);
}

export function date(iso: string, lang: Lang): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Intl.DateTimeFormat(lang === "ar" ? "ar-MR" : "fr-FR", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(y, m - 1, d)));
}

export function daysUntil(iso: string): number {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const target = Date.UTC(y, m - 1, d);
  const now = new Date();
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((target - today) / 86_400_000);
}

export function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

/** « 2026-11 » → « novembre 2026 ». */
export function month(period: string, lang: Lang): string {
  const [y, m] = period.split("-").map(Number);
  return new Intl.DateTimeFormat(lang === "ar" ? "ar-MR" : "fr-FR", { month: "long", year: "numeric", timeZone: "UTC" }).format(
    new Date(Date.UTC(y, m - 1, 1)),
  );
}

/** « 0.1500 » → « 15 % ». */
export function percent(rate: string | number, lang: Lang): string {
  return new Intl.NumberFormat(lang === "ar" ? "ar-MR" : "fr-FR", { style: "percent", maximumFractionDigits: 2 }).format(Number(rate));
}
