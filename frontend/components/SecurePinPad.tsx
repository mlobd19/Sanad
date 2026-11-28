"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import { useI18n } from "@/lib/i18n";
import { PIN_LENGTH, shuffledDigits } from "@/lib/pin";
import { ErrorLine } from "./Shell";

type Props = {
  /** Titre de l'étape (« Choisissez votre code »…), relié au pavé pour les lecteurs d'écran. */
  title: string;
  hint?: ReactNode;
  error?: string;
  busy?: boolean;
  /** Appelée au 4e chiffre (validation automatique). Pour une nouvelle étape, l'appelant change la `key`
   *  du pavé : saisie vidée et chiffres de nouveau mélangés. */
  onComplete: (pin: string) => void;
  footer?: ReactNode;
};

/**
 * Pavé numérique virtuel du code PIN : grille 3 × 4, les 10 chiffres placés au hasard à chaque affichage
 * (« Effacer » et la case vide gardent leur place). Jamais de champ de saisie ni de clavier du téléphone :
 * aucune suggestion, aucune mémorisation. Quatre points pour la saisie, aucun chiffre affiché, et aucune
 * surbrillance de la touche touchée (une capture d'écran ne révèle rien), seulement un bref retour tactile.
 */
export function SecurePinPad({ title, hint, error, busy = false, onComplete, footer }: Props) {
  const { t } = useI18n();
  // Mélange après le premier rendu : le rendu serveur ne connaît pas l'ordre (pas d'écart d'hydratation).
  const [digits, setDigits] = useState<string[] | null>(null);
  const [count, setCount] = useState(0);
  const entered = useRef(""); // le code en cours, en mémoire seulement
  const titleId = useId();

  useEffect(() => {
    setDigits(shuffledDigits());
    return () => { entered.current = ""; };
  }, []);

  function press(digit: string) {
    if (busy || entered.current.length >= PIN_LENGTH) return;
    navigator.vibrate?.(10);
    entered.current += digit;
    setCount(entered.current.length);
    if (entered.current.length === PIN_LENGTH) onComplete(entered.current);
  }

  function erase() {
    if (busy || !entered.current) return;
    navigator.vibrate?.(10);
    entered.current = entered.current.slice(0, -1);
    setCount(entered.current.length);
  }

  // Cases 1 à 9, case vide, case 10, « Effacer » : 10 chiffres mélangés, les deux autres cases fixes.
  const cells: (string | "empty" | "erase")[] = digits
    ? [...digits.slice(0, 9), "empty", digits[9], "erase"]
    : [...Array<string>(9).fill(""), "empty", "", "erase"];

  return (
    <div className="pin-step">
      <div className="pin-intro">
        <h2 className="title" id={titleId}>{title}</h2>
        {hint && <p className="ink2">{hint}</p>}
      </div>
      {/* Points et message au milieu de l'espace libre, entre le titre et le pavé. */}
      <div className="pin-entry">
        <div className="pin-dots" aria-hidden="true">
          {Array.from({ length: PIN_LENGTH }, (_, i) => <span key={i} className={i < count ? "on" : ""} />)}
        </div>
        <p className="sr-only" aria-live="polite">{t("pinProgress", { n: count })}</p>
        <ErrorLine message={error} style={{ textAlign: "center" }} />
      </div>
      <div className="pinpad" role="group" aria-labelledby={titleId} dir="ltr" aria-busy={busy}>
        {cells.map((cell, i) =>
          cell === "empty" ? (
            <span key="empty" aria-hidden="true" />
          ) : cell === "erase" ? (
            <button key="erase" type="button" className="pin-erase" onClick={erase} disabled={busy || count === 0}
              aria-label={t("pinEraseLabel")}>
              {t("pinErase")}
            </button>
          ) : (
            <button key={`k${i}`} type="button" onClick={() => press(cell)} disabled={busy || !cell}
              aria-label={cell || undefined}>
              {cell}
            </button>
          ),
        )}
      </div>
      {footer}
    </div>
  );
}
