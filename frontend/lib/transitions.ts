import { screenFor } from "./screens";

/**
 * Types de transition de vue (React <ViewTransition>, addTransitionType) :
 * - nav-forward : on avance dans le parcours (glissement vers la gauche, vers la droite en arabe) ;
 * - nav-back : on revient en arrière (sens inverse) ;
 * - nav-tab : entre deux onglets (barre du bas, onglets de l'espace entreprise) : simple fondu.
 * Sans type (bouton retour du navigateur, redirection d'un garde-fou), aucune animation.
 * Les animations elles-mêmes sont dans app/globals.css (« Transitions entre écrans »).
 */
export type NavType = "nav-forward" | "nav-back" | "nav-tab";

/** Sens d'une navigation d'une adresse à une autre, d'après la profondeur des écrans (lib/screens.ts). */
export function navTypes(from: string, to: string): NavType[] {
  const a = screenFor(from);
  const b = screenFor(to);
  if (!a || !b || a.screen === b.screen) return [];
  if (a.screen.tab && b.screen.tab) return ["nav-tab"];
  if (b.screen.depth > a.screen.depth) return ["nav-forward"];
  if (b.screen.depth < a.screen.depth) return ["nav-back"];
  return ["nav-tab"];
}

/** Classes d'animation de l'écran qui entre ou qui sort, selon le type de la transition. */
export const SCREEN_ANIMATION = {
  "nav-forward": "nav-forward",
  "nav-back": "nav-back",
  "nav-tab": "nav-fade",
  default: "none",
} as const;
