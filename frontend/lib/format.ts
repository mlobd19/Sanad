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

/** Date courte, sans l'année : « 26 janv. », « ٢٦ يناير » (carte d'un voyage). */
export function shortDate(iso: string, lang: Lang): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Intl.DateTimeFormat(lang === "ar" ? "ar-MR" : "fr-FR", { day: "numeric", month: "short" })
    .format(new Date(y, m - 1, d));
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

// --- Immatriculations ----------------------------------------------------------------------
// Mauritanie : 4 chiffres, 2 lettres, 2 chiffres (wilaya). Enregistrée « 6602BA00 », affichée « 66 02 BA 00 ».

/** Forme enregistrée : majuscules, sans espaces ni tirets. */
export function cleanPlate(value: string): string {
  return (value ?? "").toUpperCase().replace(/[\s\-.·/]+/g, "");
}

/** Affichage : « 6602BA00 » → « 66 02 BA 00 » ; tout autre format reste tel quel. */
export function formatPlate(value: string): string {
  const m = cleanPlate(value).match(/^(\d{2})(\d{2})([A-Z]{2})(\d{2})$/);
  return m ? m.slice(1).join(" ") : value ?? "";
}

/** Pendant la saisie : lettres en capitales et groupes posés au fil de la frappe (« 6602ba0 » → « 66 02 BA 0 »).
 *  Une plaque d'un autre format est seulement mise en capitales. */
export function plateInput(raw: string): string {
  const value = cleanPlate(raw).replace(/[^0-9A-Z]/g, "");
  const m = value.match(/^(\d{0,2})(\d{0,2})([A-Z]{0,2})(\d{0,2})$/);
  const fits = m && (m[2] === "" || m[1].length === 2) && (m[3] === "" || m[2].length === 2)
    && (m[4] === "" || m[3].length === 2);
  return fits ? m.slice(1).filter(Boolean).join(" ") : raw.toUpperCase();
}

// --- Téléphones ----------------------------------------------------------------------------
// Numéros mauritaniens : enregistrés « +22236000001 », affichés « 36 00 00 01 » (Sanad n'existe qu'en
// Mauritanie : l'indicatif +222 n'est jamais affiché ni saisi, il est ajouté à l'envoi).

/** Les 8 chiffres locaux d'un numéro mauritanien (« +222 36 00 00 01 » ou « 0022236000001 » → « 36000001 »). */
export function localPhone(value: string): string {
  const digits = (value ?? "").replace(/\D/g, "").replace(/^(00)?222(?=\d{8}$)/, "");
  return digits.slice(0, 8);
}

/** Chiffres locaux groupés par deux, pendant la saisie : « 3600000 » → « 36 00 00 0 ». */
export function groupPhone(local: string): string {
  return localPhone(local).replace(/(\d{2})(?=\d)/g, "$1 ");
}

/** Affichage : « +22236000001 » ou « 36000001 » → « 36 00 00 01 ». Tout autre format reste tel quel. */
export function formatPhone(value: string): string {
  const digits = (value ?? "").replace(/\D/g, "");
  const local = digits.length === 11 && digits.startsWith("222") ? digits.slice(3) : digits.length === 8 ? digits : "";
  return local ? local.replace(/(\d{2})(?=\d)/g, "$1 ") : value ?? "";
}

/** Nom du client : en arabe en mode arabe s'il a été fourni par l'ANRPTS, sinon en caractères latins. */
export function displayName(user: { full_name: string; full_name_ar?: string }, lang: Lang): string {
  return (lang === "ar" && user.full_name_ar) || user.full_name;
}
