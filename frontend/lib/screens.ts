import type { Key } from "./i18n";

/**
 * Écrans de l'app client : barre du haut (titre, retour, étape) et barre du bas, rendues une seule
 * fois par le layout partagé (app/(client)/layout.tsx), et profondeur dans le parcours, qui donne
 * le sens des transitions (lib/transitions.ts).
 *
 * Profondeur : accueil 0 → véhicule 1 → devis 2 → paiement 3 → contrat 4 → sinistre ou contrôle 5.
 * Voyage : accueil 0 → voyage 1 → voyageurs 1,5 → offres 2 → paiement 3 (le même écran que l'auto).
 * Les trois onglets (accueil, contrats, profil) sont au niveau 0.
 */

/** Parcours de souscription : ses étapes s'affichent sous le titre (components/Shell.tsx, Stepper). */
export type Flow = "auto" | "travel";
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
  /** Parcours de l'étape ; absent : celui que l'écran indique (paiement, commun à l'auto et au voyage). */
  flow?: Flow;
  /** Étape de cet écran commun dans le parcours voyage (paiement : 3, après voyage, voyageurs, offre). */
  travelStep?: number;
  /** Plein écran, sans barre (affichage pour un contrôle routier). */
  bare?: boolean;
};

const SCREENS: { pattern: RegExp; params: string[]; screen: Screen }[] = [
  { pattern: /^\/$/, params: [], screen: { id: "home", depth: 0, tab: true } },
  { pattern: /^\/contrats$/, params: [], screen: { id: "contracts", depth: 0, tab: true, title: "myContracts" } },
  { pattern: /^\/profil$/, params: [], screen: { id: "profile", depth: 0, tab: true, title: "profileTitle" } },
  { pattern: /^\/profil\/code$/, params: [],
    screen: { id: "pinChange", depth: 1, title: "pinChangeTitle", back: () => "/profil" } },
  { pattern: /^\/vehicule$/, params: [], screen: { id: "vehicle", depth: 1, title: "vehicleTitle", back: () => "/", step: 0 } },
  { pattern: /^\/devis\/([^/]+)$/, params: ["assetId"],
    screen: { id: "quotes", depth: 2, title: "quotesTitle", back: () => "/vehicule", step: 1 } },
  { pattern: /^\/voyage$/, params: [],
    screen: { id: "trip", depth: 1, title: "travelTitle", back: () => "/", step: 0, flow: "travel" } },
  { pattern: /^\/voyage\/([^/]+)\/voyageurs$/, params: ["tripId"],
    screen: { id: "travelers", depth: 1.5, title: "travelersTitle", back: () => "/voyage", step: 1, flow: "travel" } },
  { pattern: /^\/voyage\/([^/]+)\/offres$/, params: ["tripId"],
    screen: { id: "travelQuotes", depth: 2, title: "quotesTitle", back: (p) => `/voyage/${p.tripId}/voyageurs`, step: 2,
      flow: "travel" } },
  { pattern: /^\/paiement\/([^/]+)$/, params: ["policyId"],
    screen: { id: "payment", depth: 3, title: "payTitle", back: () => "/", step: 2, travelStep: 3 } },
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
