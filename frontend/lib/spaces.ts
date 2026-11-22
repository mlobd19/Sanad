"use client";

/**
 * Porte d'entrée unique : chaque compte a un seul espace, et une seule page de connexion (/connexion).
 * Toute redirection liée au rôle passe par ce fichier.
 */
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, ApiError, getToken, setToken, type User } from "@/lib/api";

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

/**
 * Garde-fou commun à tous les espaces :
 * non connecté → /connexion (bon onglet) ; autre rôle → son propre espace ; sinon, le compte connecté.
 */
export function useSpace(expected: Role) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => {
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
        if (err instanceof ApiError && err.status === 401) setToken(null); // jeton expiré ou révoqué
        router.replace(loginUrl(expected));
      });
  }, [router, expected]);
  return { user, setUser };
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
      .catch(() => {
        setToken(null);
        setState("anonymous");
      });
  }, [router]);
  return state;
}

/** Vrai / faux une fois le navigateur lu (null pendant le rendu serveur : pas d'écart d'hydratation). */
export function useHasToken(): boolean | null {
  const [has, setHas] = useState<boolean | null>(null);
  useEffect(() => setHas(Boolean(getToken())), []);
  return has;
}
