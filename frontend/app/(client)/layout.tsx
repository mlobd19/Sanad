import type { ReactNode } from "react";

import { ClientChrome } from "@/components/ClientChrome";

/** Layout partagé de l'app client (accueil, véhicule, devis, paiement, contrats, profil) :
 *  il persiste d'un écran à l'autre, avec sa barre du haut et sa barre du bas. */
export default function ClientLayout({ children }: { children: ReactNode }) {
  return <ClientChrome>{children}</ClientChrome>;
}
