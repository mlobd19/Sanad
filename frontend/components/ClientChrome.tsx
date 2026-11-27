"use client";

import { usePathname } from "next/navigation";
import { createContext, useContext, useLayoutEffect, useState, ViewTransition, type ReactNode } from "react";

import { useI18n } from "@/lib/i18n";
import { screenFor } from "@/lib/screens";
import { SpaceProvider, useHasToken } from "@/lib/spaces";
import { SCREEN_ANIMATION } from "@/lib/transitions";

import { BottomNav, Stepper, TopBar } from "./Shell";

/** Un écran peut remplacer la barre du haut par son propre en-tête (contrat assuré : en-tête vert). */
const HideTopBar = createContext<(hidden: boolean) => void>(() => undefined);

/** Masque la barre du haut tant que `hidden` est vrai (avant l'affichage : pas de clignement). */
export function useHideTopBar(hidden: boolean) {
  const setHidden = useContext(HideTopBar);
  useLayoutEffect(() => {
    setHidden(hidden);
    return () => setHidden(false);
  }, [hidden, setHidden]);
}

/**
 * Cadre commun des écrans de l'app client : garde-fou du compte (lib/spaces.ts), barre du haut et
 * barre du bas créées une seule fois (elles ne sont pas recréées à chaque navigation et ne
 * s'animent pas), et l'écran lui-même dans une transition de vue (lib/transitions.ts).
 */
export function ClientChrome({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const pathname = usePathname();
  const hasToken = useHasToken();
  const [topBarHidden, setTopBarHidden] = useState(false);
  const found = screenFor(pathname);
  const screen = found?.screen;
  // Accueil : page d'un visiteur sans compte ; tous les autres écrans demandent un compte client.
  const guarded = screen?.id === "home" ? hasToken === true : true;
  const showTopBar = screen?.title && !screen.bare && !topBarHidden;
  const showBottomNav = screen?.tab && hasToken === true;

  return (
    <SpaceProvider role="customer" enabled={guarded}>
      <HideTopBar.Provider value={setTopBarHidden}>
        <div className="app">
          {showTopBar && found && screen.title && (
            <TopBar title={t(screen.title)} back={screen.back?.(found.params)}>
              {screen.step !== undefined && <Stepper current={screen.step} />}
            </TopBar>
          )}
          {/* Une clé par adresse : l'écran qui part et celui qui arrive s'animent selon le type
              de la navigation (avancer, revenir, onglet) ; sans type, aucune animation. */}
          <ViewTransition key={pathname} enter={SCREEN_ANIMATION} exit={SCREEN_ANIMATION} default="none">
            <div className="screen">{children}</div>
          </ViewTransition>
          {showBottomNav && <BottomNav />}
        </div>
      </HideTopBar.Provider>
    </SpaceProvider>
  );
}
