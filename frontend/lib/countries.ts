import COUNTRIES from "./countries.json";
import type { Lang } from "./i18n";

/**
 * Pays de destination d'un voyage (codes ISO 3166-1, Mauritanie exclue) avec leur nom en français,
 * en arabe et en anglais. Même fichier que le backend (backend/apps/policies/countries.json), qui
 * valide les codes et imprime les noms sur l'attestation.
 */
export type Country = { code: string; fr: string; ar: string; en: string };

const BY_CODE = new Map((COUNTRIES as Country[]).map((c) => [c.code, c]));

export function countryName(code: string, lang: Lang): string {
  return BY_CODE.get(code)?.[lang] ?? code;
}

/** Tous les pays, dans l'ordre alphabétique de la langue affichée. */
export function countryList(lang: Lang): Country[] {
  return [...(COUNTRIES as Country[])].sort((a, b) => a[lang].localeCompare(b[lang], lang));
}

/** Recherche sans accents ni majuscules, dans les trois langues (« espa », « إسبا », « spain »). */
export function searchCountries(query: string, lang: Lang, limit = 8): Country[] {
  const q = fold(query);
  if (!q) return [];
  return countryList(lang)
    .filter((c) => [c.fr, c.ar, c.en, c.code].some((name) => fold(name).includes(q)))
    .sort((a, b) => Number(!fold(a[lang]).startsWith(q)) - Number(!fold(b[lang]).startsWith(q)))
    .slice(0, limit);
}

function fold(value: string): string {
  return value.normalize("NFD").replace(/[̀-ًͯ-ٟ]/g, "").toLowerCase().trim();
}

/** « Espagne », « Espagne, France » ou, au-delà de `max`, « Espagne +2 ». */
export function destinationsLabel(codes: string[], lang: Lang, max = 2): string {
  const names = codes.map((c) => countryName(c, lang));
  if (names.length <= max) return names.join(lang === "ar" ? "، " : ", ");
  // « +2 » isolé de gauche à droite (sinon « 2+ » en arabe), chiffres de la langue.
  const more = new Intl.NumberFormat(lang === "ar" ? "ar-MR" : "fr-FR").format(names.length - 1);
  return `${names[0]} \u2066+${more}\u2069`;
}
