"use client";

import { useEffect, useState } from "react";

import { Icon } from "@/components/Icon";
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

/** Bouton soleil / lune à côté du bouton des langues : bascule entre clair et sombre.
 *  Lune = passer en sombre, soleil = passer en clair. « Automatique » se choisit dans le Profil. */
export function ThemeIconButton() {
  const { t } = useI18n();
  const [choice, setChoice] = useTheme();
  const [systemDark, setSystemDark] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    setSystemDark(media.matches);
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  const dark = choice === "dark" || (choice === "auto" && systemDark);
  const label = t(dark ? "themeToLight" : "themeToDark");
  return (
    <button type="button" className="btn-on-dark icon-only" onClick={() => setChoice(dark ? "light" : "dark")}
      aria-label={label} title={label}>
      <Icon name={dark ? "sun" : "moon"} size={20} strokeWidth={2} />
    </button>
  );
}
