"use client";

/**
 * Porte d'entrée unique : chaque compte a un seul espace, et une seule page de connexion (/connexion).
 * Toute redirection liée au rôle passe par ce fichier.
 */
import { useRouter } from "next/navigation";
import { createContext, createElement, useContext, useEffect, useState, type ReactNode } from "react";

import { api, ApiError, getToken, isPinGate, pinUrl, setToken, type User } from "@/lib/api";

export type Role = "customer" | "company_member" | "insurer_agent" | "staff";

/** Espace de chaque rôle. Le back-office (/admin/) est servi par Django, hors de l'app Next.js. */
const HOMES: Record<Role, string> = {
  customer: "/",
  company_member: "/entreprise",
  insurer_agent: "/assureur",
  staff: "/admin/",
};

const PRO_ROLES: Role[] = ["company_member", "insurer_agent"];

/** Onglet de /connexion : « particulier » (téléphone + SMS) ou « pro » (email + mot de passe + SMS). */
export type LoginTab = "particulier" | "pro";

export function homeFor(role: string): string {
  return HOMES[role as Role] ?? "/connexion";
}

/** Page de connexion, sur l'onglet qui convient à l'espace demandé. */
export function loginUrl(role?: Role): string {
  return role && PRO_ROLES.includes(role) ? "/connexion?espace=pro" : "/connexion";
}

type Navigate = { replace: (href: string) => void };

/** Va dans un espace : routeur Next.js pour l'app, chargement complet pour le back-office Django. */
export function goTo(router: Navigate, href: string) {
  if (href.startsWith("/admin")) window.location.assign(href);
  else router.replace(href);
}

/** Envoie le compte dans son espace. Un compte équipe n'a pas de session dans l'app : il passe par /admin/. */
export function enterSpace(router: Navigate, user: Pick<User, "role">) {
  if (user.role === "staff") setToken(null);
  goTo(router, homeFor(user.role));
}

/** Déconnexion depuis n'importe quel espace : retour à la page de connexion unique. */
export async function logout(router: Navigate, role?: Role) {
  // Le jeton est d'abord supprimé côté serveur : même copié, il ne vaut plus rien.
  const token = getToken();
  if (token) {
    await fetch("/api/auth/logout", { method: "POST", headers: { Authorization: `Token ${token}` } })
      .catch(() => undefined); // hors ligne : il expirera de lui-même
  }
  setToken(null);
  router.replace(loginUrl(role));
}

type SpaceValue = { user: User | null; setUser: (user: User) => void };
type SpaceContextValue = SpaceValue & { role: Role };

/** Compte confirmé par le garde-fou du layout partagé (app/(client)/layout.tsx), pour tous ses écrans. */
const SpaceContext = createContext<SpaceContextValue | null>(null);

function useGuard(expected: Role, enabled: boolean): SpaceValue {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => {
    if (!enabled) return;
    if (!getToken()) {
      router.replace(loginUrl(expected));
      return;
    }
    api<User>("me")
      .then((me) => {
        if (me.role === expected) setUser(me);
        else enterSpace(router, me);
      })
      .catch((err) => {
        if (err instanceof ApiError && isPinGate(err.status, err.code)) return; // api() ouvre l'écran du code PIN
        if (err instanceof ApiError && err.status === 401) setToken(null); // jeton expiré ou révoqué
        router.replace(loginUrl(expected));
      });
  }, [router, expected, enabled]);
  return { user, setUser };
}

/**
 * Garde-fou commun à tous les espaces :
 * non connecté → /connexion (bon onglet) ; autre rôle → son propre espace ; sinon, le compte connecté.
 * Sous un SpaceProvider du même rôle, le compte vient du layout : pas de nouvelle vérification
 * à chaque écran (la navigation reste instantanée).
 */
export function useSpace(expected: Role): SpaceValue {
  const shared = useContext(SpaceContext);
  const inherited = shared?.role === expected ? shared : null;
  const own = useGuard(expected, !inherited);
  return inherited ?? own;
}

/** Garde-fou posé une fois par un layout pour tous ses écrans. `enabled` faux : pas de garde-fou
 *  (page d'accueil d'un visiteur), les écrans retombent alors sur le leur. */
export function SpaceProvider({ role, enabled, children }: { role: Role; enabled: boolean; children: ReactNode }) {
  const value = useGuard(role, enabled);
  return createElement(SpaceContext.Provider, { value: enabled ? { ...value, role } : null }, children);
}

/** Sur /connexion et la page d'accueil : un compte déjà connecté va directement dans son espace.
 *  Renvoie "checking" tant que la vérification est en cours, puis "anonymous". */
export function useRedirectIfLoggedIn(): "checking" | "anonymous" {
  const router = useRouter();
  const [state, setState] = useState<"checking" | "anonymous">("checking");
  useEffect(() => {
    if (!getToken()) {
      setState("anonymous");
      return;
    }
    api<User>("me")
      .then((me) => {
        enterSpace(router, me);
        if (me.role === "staff") setState("anonymous");
      })
      .catch((err) => {
        // Particulier dont la session du code PIN est fermée : écran du code, sans SMS.
        if (err instanceof ApiError && isPinGate(err.status, err.code)) {
          router.replace(pinUrl());
          return;
        }
        setToken(null);
        setState("anonymous");
      });
  }, [router]);
  return state;
}

/** Écran où revenir après le code PIN : une adresse de l'app client seulement (jamais un autre site). */
export function safeReturn(value: string | null): string {
  return value && /^\/(?![/\\])/.test(value) && !value.startsWith("/connexion") ? value : HOMES.customer;
}

/** Vrai / faux une fois le navigateur lu (null pendant le rendu serveur : pas d'écart d'hydratation). */
export function useHasToken(): boolean | null {
  const [has, setHas] = useState<boolean | null>(null);
  useEffect(() => setHas(Boolean(getToken())), []);
  return has;
}
