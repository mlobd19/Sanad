"use client";

import { usePathname } from "next/navigation";
import type { CSSProperties, ReactNode } from "react";

import { useI18n } from "@/lib/i18n";

import { Icon } from "./Icon";
import { Link } from "./NavLink";

/** Barre du haut, rendue une seule fois par le layout de l'app client (app/(client)/layout.tsx).
 *  Nom de transition fixe : elle ne glisse pas avec l'écran (app/globals.css). */
export function TopBar({ title, back, children }: { title: string; back?: string; children?: ReactNode }) {
  const { t } = useI18n();
  return (
    <header className="topbar" style={{ viewTransitionName: "sn-topbar" }}>
      <div className="head">
        {back && (
          <Link href={back} className="iconbtn" aria-label={t("back")}>
            <Icon name="back" size={24} strokeWidth={2.2} />
          </Link>
        )}
        <h1>{title}</h1>
      </div>
      {children}
    </header>
  );
}

/** Barre du bas des trois onglets, rendue une seule fois par le layout de l'app client. */
export function BottomNav() {
  const { t } = useI18n();
  const path = usePathname();
  const items = [
    { href: "/", label: t("navHome"), icon: "home" },
    { href: "/contrats", label: t("navContracts"), icon: "file" },
    { href: "/profil", label: t("navProfile"), icon: "user" },
  ];
  return (
    <nav className="bottomnav" aria-label="Navigation principale" style={{ viewTransitionName: "sn-bottomnav" }}>
      {items.map((item) => {
        const active = item.href === "/" ? path === "/" : path.startsWith(item.href);
        return (
          <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined}>
            <Icon name={item.icon} strokeWidth={2} />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

/** Bloc gris aux dimensions du contenu attendu, pendant le premier chargement d'un écran. */
export function Skeleton({ width = "100%", height = 16, radius = 8, style }: {
  width?: number | string; height?: number | string; radius?: number; style?: CSSProperties;
}) {
  return <span className="skeleton" aria-hidden="true" style={{ width, height, borderRadius: radius, ...style }} />;
}

/** Écran en cours de chargement : squelettes (enfants) annoncés aux lecteurs d'écran. */
export function SkeletonGroup({ children, className, style }: { children: ReactNode; className?: string; style?: CSSProperties }) {
  const { t } = useI18n();
  return (
    <div className={className} style={style} role="status" aria-busy="true">
      <span className="sr-only">{t("loading")}</span>
      {children}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <div className="banner red" role="alert">
      <span className="grow">{message || t("error")}</span>
      {onRetry && (
        <button type="button" className="btn outline" onClick={onRetry}>
          {t("retry")}
        </button>
      )}
    </div>
  );
}

/** Message d'erreur d'un formulaire : sa ligne est toujours là (vide sans erreur), pour que le
 *  contenu ne saute pas quand il apparaît. Annoncé aux lecteurs d'écran dès qu'il change. */
export function ErrorLine({ message, style }: { message?: string; style?: CSSProperties }) {
  return <p className="error error-slot" role="alert" style={style}>{message}</p>;
}

/** Étapes nommées du parcours de souscription : 0 véhicule, 1 offre, 2 paiement, 3 attestation. */
export function Stepper({ current }: { current: number }) {
  const { t } = useI18n();
  const labels = [t("stepVehicle"), t("stepOffer"), t("stepPay"), t("stepAttestation")];
  return (
    <ol className="stepper" aria-label="Étapes">
      {labels.map((label, i) => {
        const state = i < current ? "done" : i === current ? "current" : "";
        return (
          <li key={label} className={state} aria-current={i === current ? "step" : undefined}>
            <span className="dot">{i < current ? <Icon name="check" size={16} strokeWidth={3} /> : i + 1}</span>
            {label}
          </li>
        );
      })}
    </ol>
  );
}

export function StatusPill({ status }: { status: string }) {
  const { t } = useI18n();
  const tone = status === "active" ? "" : status === "paid" || status === "draft" ? "warn" : status === "refused" ? "bad" : "quiet";
  return <span className={`pill ${tone}`}>{t(`status_${status}` as Parameters<typeof t>[0])}</span>;
}
