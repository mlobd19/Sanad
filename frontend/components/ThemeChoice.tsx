"use client";

import { useI18n, type Key } from "@/lib/i18n";
import { THEME_CHOICES, useTheme, type ThemeChoice } from "@/lib/theme";

const LABELS: Record<ThemeChoice, Key> = { auto: "themeAuto", light: "themeLight", dark: "themeDark" };

/** Choix « Automatique / Clair / Sombre » (Profil de l'app client). */
export function ThemeChoicePicker() {
  const { t } = useI18n();
  const [choice, setChoice] = useTheme();
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="segmented" role="radiogroup" aria-label={t("theme")} aria-describedby="theme-hint">
        {THEME_CHOICES.map((c) => (
          <button key={c} type="button" role="radio" aria-checked={choice === c} className="radio"
            style={{ justifyContent: "center", minHeight: 48 }} onClick={() => setChoice(c)}>
            {t(LABELS[c])}
          </button>
        ))}
      </div>
      <span id="theme-hint" className="small muted">{t("themeHint")}</span>
    </div>
  );
}

/** Bouton compact pour les en-têtes des espaces pro : passe d'un choix au suivant. */
export function ThemeToggleButton() {
  const { t } = useI18n();
  const [choice, setChoice] = useTheme();
  const next = THEME_CHOICES[(THEME_CHOICES.indexOf(choice) + 1) % THEME_CHOICES.length];
  return (
    <button type="button" className="btn-on-dark" onClick={() => setChoice(next)}
      aria-label={t("themeButtonLabel", { mode: t(LABELS[choice]), next: t(LABELS[next]) })}>
      {t("themeButton", { mode: t(LABELS[choice]) })}
    </button>
  );
}
