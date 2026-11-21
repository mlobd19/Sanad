"use client";

/**
 * Apparence : « auto » suit le réglage de l'appareil (prefers-color-scheme), « light » et « dark » le forcent.
 * Le choix est gardé sur l'appareil ; app/layout.tsx le pose sur <html data-theme> avant l'affichage
 * (pas d'éclair blanc au chargement). Les couleurs sont dans app/globals.css.
 */
import { useCallback, useEffect, useState } from "react";

export type ThemeChoice = "auto" | "light" | "dark";
export const THEME_CHOICES: ThemeChoice[] = ["auto", "light", "dark"];

const KEY = "sanad.theme";
const EVENT = "sanad:theme";

/** Script exécuté dans <head> avant le rendu : applique le choix enregistré. */
export const THEME_BOOT_SCRIPT =
  `try{var t=localStorage.getItem("${KEY}");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

function read(): ThemeChoice {
  try {
    const saved = localStorage.getItem(KEY);
    return saved === "light" || saved === "dark" ? saved : "auto";
  } catch {
    return "auto";
  }
}

function apply(choice: ThemeChoice) {
  if (choice === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = choice;
}

/** Choix d'apparence, partagé entre tous les composants de la page. */
export function useTheme(): [ThemeChoice, (choice: ThemeChoice) => void] {
  const [choice, setChoice] = useState<ThemeChoice>("auto");

  useEffect(() => {
    setChoice(read());
    const sync = () => setChoice(read());
    window.addEventListener(EVENT, sync);
    window.addEventListener("storage", sync); // autre onglet
    return () => {
      window.removeEventListener(EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const update = useCallback((next: ThemeChoice) => {
    try {
      if (next === "auto") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, next);
    } catch {
      /* navigation privée : le choix vaut pour cette page seulement */
    }
    apply(next);
    setChoice(next);
    window.dispatchEvent(new Event(EVENT));
  }, []);

  return [choice, update];
}
