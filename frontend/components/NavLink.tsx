"use client";

import NextLink from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useMemo, type ComponentProps } from "react";

import { navTypes } from "@/lib/transitions";

/**
 * Lien de l'app : celui de Next.js (préchargement), avec le sens de la transition de vue
 * (avancer, revenir, changer d'onglet) calculé d'après les écrans de départ et d'arrivée.
 * À utiliser pour toute navigation ; router.push seulement après une action (useNav).
 */
export function Link({ href, transitionTypes, ...props }: ComponentProps<typeof NextLink>) {
  const path = usePathname();
  const target = typeof href === "string" ? href : href.pathname ?? "";
  return <NextLink href={href} transitionTypes={transitionTypes ?? navTypes(path, target)} {...props} />;
}

/** Navigation après une action (paiement, envoi d'un formulaire), avec le même sens de transition. */
export function useNav() {
  const router = useRouter();
  const path = usePathname();
  return useMemo(
    () => ({
      push: (href: string) => router.push(href, { transitionTypes: navTypes(path, href) }),
      replace: (href: string) => router.replace(href, { transitionTypes: navTypes(path, href) }),
    }),
    [router, path],
  );
}
