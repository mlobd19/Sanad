"use client";

import { Icon } from "@/components/Icon";
import { useI18n } from "@/lib/i18n";

/** Bouton globe des en-têtes : passe du français à l'arabe et inversement.
 *  Le libellé annonce la langue de destination (lecteurs d'écran, bulle au survol). */
export function LanguageButton() {
  const { t, lang, setLang } = useI18n();
  const label = t("switchLanguage");
  return (
    <button type="button" className="btn-on-dark icon-only" onClick={() => setLang(lang === "fr" ? "ar" : "fr")}
      aria-label={label} title={label}>
      <Icon name="globe" size={20} strokeWidth={2} />
    </button>
  );
}
