import type { Key } from "./i18n";

/**
 * Écrans de l'app client : barre du haut (titre, retour, étape) et barre du bas, rendues une seule
 * fois par le layout partagé (app/(client)/layout.tsx), et profondeur dans le parcours, qui donne
 * le sens des transitions (lib/transitions.ts).
 *
 * Profondeur : accueil 0 → véhicule 1 → devis 2 → paiement 3 → contrat 4 → sinistre ou contrôle 5.
 * Les trois onglets (accueil, contrats, profil) sont au niveau 0.
 */
export type Screen = {
  id: string;
  depth: number;
  /** Onglet de la barre du bas : entre deux onglets, simple fondu. */
  tab?: boolean;
  /** Barre du haut : titre et lien retour (`back`, avec les paramètres de l'adresse). */
  title?: Key;
  back?: (params: Record<string, string>) => string;
  /** Étape du parcours de souscription affichée sous le titre (0 véhicule … 3 attestation). */
  step?: number;
  /** Plein écran, sans barre (affichage pour un contrôle routier). */
  bare?: boolean;
};

const SCREENS: { pattern: RegExp; params: string[]; screen: Screen }[] = [
  { pattern: /^\/$/, params: [], screen: { id: "home", depth: 0, tab: true } },
  { pattern: /^\/contrats$/, params: [], screen: { id: "contracts", depth: 0, tab: true, title: "myContracts" } },
  { pattern: /^\/profil$/, params: [], screen: { id: "profile", depth: 0, tab: true, title: "profileTitle" } },
  { pattern: /^\/vehicule$/, params: [], screen: { id: "vehicle", depth: 1, title: "vehicleTitle", back: () => "/", step: 0 } },
  { pattern: /^\/devis\/([^/]+)$/, params: ["assetId"],
    screen: { id: "quotes", depth: 2, title: "quotesTitle", back: () => "/vehicule", step: 1 } },
  { pattern: /^\/paiement\/([^/]+)$/, params: ["policyId"],
    screen: { id: "payment", depth: 3, title: "payTitle", back: () => "/", step: 2 } },
  { pattern: /^\/contrats\/([^/]+)$/, params: ["policyId"],
    screen: { id: "contract", depth: 4, title: "contractTitle", back: () => "/contrats" } },
  { pattern: /^\/contrats\/([^/]+)\/sinistre$/, params: ["policyId"],
    screen: { id: "claim", depth: 5, title: "declareClaim", back: (p) => `/contrats/${p.policyId}` } },
  { pattern: /^\/contrats\/([^/]+)\/controle$/, params: ["policyId"], screen: { id: "control", depth: 5, bare: true } },
];

/** Écran d'une adresse (« /devis/12?duree=6 » → devis), ou null hors de l'app client. */
export function screenFor(href: string): { screen: Screen; params: Record<string, string> } | null {
  const path = href.split(/[?#]/)[0].replace(/(.)\/$/, "$1");
  for (const { pattern, params, screen } of SCREENS) {
    const match = pattern.exec(path);
    if (match) return { screen, params: Object.fromEntries(params.map((name, i) => [name, match[i + 1]])) };
  }
  return null;
}
