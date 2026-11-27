"use client";

import { useId } from "react";

import { useI18n } from "@/lib/i18n";

// Logo « l'arche et l'élan » : l'arche protège, la courbe s'élance et en sort. On avance, couvert.
// Même tracé partout : icône de l'app (public/icon.svg), attestation PDF (attestations/pdf.py),
// back-office (admin/base_site.html) et page de vérification (attestations/verify.html).

export const ARCH = "M14 70A34 34 0 0 1 82 70";
export const ELAN = "M20 80C40 78 52 64 60 50C64 43 68 37 73 32";

/** Nom latin et nom arabe du logo empilé : ils font partie du dessin, comme le symbole. */
const BRAND = "Sanad";
const BRAND_AR = "سند";

type MarkProps = { size?: number; color?: string; title?: string };

/** Symbole seul. Trait en currentColor (`color`, par défaut --green), point toujours --sand.
 *  L'élan coupe l'arche par un masque (jamais par un trait couleur du fond) : juste sur tous les fonds. */
export function SanadMark({ size = 32, color = "var(--green)", title }: MarkProps) {
  const mask = `arche-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`; // un masque par instance
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 96 96"
      style={{ color, flexShrink: 0 }}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      <defs>
        <mask id={mask}>
          <rect width="96" height="96" fill="white" />
          <path d={ELAN} stroke="black" strokeWidth="15" strokeLinecap="round" fill="none" />
        </mask>
      </defs>
      <path d={ARCH} mask={`url(#${mask})`} fill="none" stroke="currentColor" strokeWidth="7" strokeLinecap="round" />
      <path d={ELAN} fill="none" stroke="currentColor" strokeWidth="7" strokeLinecap="round" />
      <circle cx="80" cy="24" r="7" fill="var(--sand)" />
    </svg>
  );
}

/** Symbole + nom sur une ligne. `onDark` : version en-tête, blanche sur le vert profond. */
export function Wordmark({ name, size = 18, onDark = false }: { name: string; size?: number; onDark?: boolean }) {
  return (
    <span className="wordmark" style={{ fontSize: size, color: onDark ? "#fff" : "var(--ink)" }}>
      <SanadMark size={size * 1.55} color={onDark ? "#fff" : "var(--green)"} />
      {name}
    </span>
  );
}

/** Version empilée et centrée : symbole et, dessous, le nom dans la langue choisie seulement
 *  (français : « Sanad » ; arabe : « سند »). `onDark` : sur le vert profond des en-têtes (symbole blanc). */
export function StackedLogo({ size = 72, onDark = false }: { size?: number; onDark?: boolean }) {
  const { lang } = useI18n();
  const ar = lang === "ar";
  return (
    <span className="logo-stacked" style={{ color: onDark ? "#fff" : "var(--ink)" }}>
      <SanadMark size={size} color={onDark ? "#fff" : "var(--green)"} />
      <span className="logo-stacked-name" style={{ fontSize: size * 0.42 }} lang={ar ? "ar" : "fr"} dir={ar ? "rtl" : "ltr"}>
        {ar ? BRAND_AR : BRAND}
      </span>
    </span>
  );
}
