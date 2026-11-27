"use client";

import { Skeleton, SkeletonGroup } from "./Shell";

// Squelettes des écrans de l'app client : mêmes cartes, mêmes marges, mêmes hauteurs que le contenu
// final, pour que rien ne saute quand les données arrivent. Affichés au tout premier chargement
// seulement : ensuite, les dernières données gardées en mémoire s'affichent (lib/cache.ts).

/** Carte de contrat du carrousel de l'accueil : illustration, plaque, statut, compagnie, bouton. */
export function ContractCardSkeleton() {
  return (
    <div className="card raised contract-card">
      <div className="row">
        <Skeleton width={76} height={35} radius={10} />
        <div className="grow stack" style={{ gap: 6 }}>
          <Skeleton width="70%" height={25} />
          <Skeleton width={70} height={26} radius={14} />
        </div>
      </div>
      <Skeleton width="80%" height={22} />
      <Skeleton height={52} radius={14} />
    </div>
  );
}

/** Accueil (sous l'en-tête vert) : le carrousel (une carte et le début de la suivante, points et
 *  « Tout voir ») puis les tuiles « Souscrire », mêmes classes et mêmes espacements que le contenu,
 *  remplacés d'un seul coup. */
export function HomeContractsSkeleton() {
  return (
    <SkeletonGroup className="stack" style={{ gap: "var(--section-gap)" }}>
      <div className="stack">
        <div className="carousel" style={{ overflow: "hidden" }}>
          <div className="carousel-item"><ContractCardSkeleton /></div>
          <div className="carousel-item"><ContractCardSkeleton /></div>
        </div>
        <div className="between carousel-foot">
          <Skeleton width={50} height={8} radius={4} />
          <Skeleton width={90} height={16} />
        </div>
      </div>
      <div className="stack">
        <Skeleton width={170} height={14} style={{ margin: "1px 0" }} />
        <div className="grid2">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} height="var(--tile-height)" radius={16} />)}
        </div>
      </div>
    </SkeletonGroup>
  );
}

/** Écran véhicule : véhicules enregistrés puis formulaire, affichés ensemble. */
export function VehicleSkeleton() {
  return (
    <SkeletonGroup className="stack" style={{ gap: 14 }}>
      <Skeleton width={120} height={14} />
      <div className="card">
        <div className="row">
          <Skeleton width={92} height={43} radius={10} />
          <div className="grow stack" style={{ gap: 6 }}>
            <Skeleton width="60%" height={20} />
            <Skeleton width="45%" height={14} />
          </div>
        </div>
      </div>
      <Skeleton height={56} radius={14} style={{ marginTop: 8 }} />
      <FormSkeleton fields={3} />
    </SkeletonGroup>
  );
}

/** Liste « Mes contrats ». */
export function ContractListSkeleton() {
  return (
    <SkeletonGroup className="stack" style={{ gap: 14 }}>
      {[0, 1, 2].map((i) => (
        <div key={i} className="card">
          <div className="row">
            <Skeleton width={48} height={48} radius={14} />
            <div className="grow stack" style={{ gap: 6 }}>
              <Skeleton width="70%" height={18} />
              <Skeleton width="50%" height={14} />
            </div>
            <Skeleton width={64} height={26} radius={14} />
          </div>
          <Skeleton width="60%" height={14} />
        </div>
      ))}
    </SkeletonGroup>
  );
}

/** Devis comparés : véhicule (s'il n'est pas déjà affiché), durée, formules, offres. */
export function QuotesSkeleton({ vehicle = true }: { vehicle?: boolean }) {
  return (
    <SkeletonGroup className="stack" style={{ gap: 14 }}>
      {vehicle && (
        <div className="row" style={{ gap: 12 }}>
          <Skeleton width={96} height={45} radius={10} />
          <div className="stack" style={{ gap: 6 }}>
            <Skeleton width={110} height={32} radius={10} />
            <Skeleton width={150} height={14} />
          </div>
        </div>
      )}
      <Skeleton height={52} radius={14} />
      <div className="row" style={{ gap: 8 }}>
        <Skeleton width={120} height={44} radius={22} />
        <Skeleton width={130} height={44} radius={22} />
        <Skeleton width={110} height={44} radius={22} />
      </div>
      {[0, 1, 2].map((i) => (
        <div key={i} className="card">
          <div className="row">
            <Skeleton width={48} height={48} radius={12} />
            <div className="grow stack" style={{ gap: 6 }}>
              <Skeleton width="45%" height={18} />
              <Skeleton width="65%" height={13} />
            </div>
            <Skeleton width={84} height={24} />
          </div>
        </div>
      ))}
    </SkeletonGroup>
  );
}

/** Paiement : montant, moyens de paiement, numéro. */
export function PaymentSkeleton() {
  return (
    <SkeletonGroup className="stack" style={{ gap: 14 }}>
      <Skeleton height={112} radius={20} />
      <Skeleton width={90} height={14} style={{ marginTop: 6 }} />
      {[0, 1, 2].map((i) => <Skeleton key={i} height={64} radius={16} />)}
      <Skeleton width={150} height={16} />
      <Skeleton height={52} radius={14} />
    </SkeletonGroup>
  );
}

/** Contrat : carte d'attestation (en-tête, QR, plaque, validité, compagnie) et boutons. */
export function ContractSkeleton() {
  return (
    <SkeletonGroup className="stack" style={{ gap: 14 }}>
      <div className="card attestation">
        <div style={{ padding: "14px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div className="stack" style={{ gap: 6 }}>
            <Skeleton width={90} height={12} />
            <Skeleton width={170} height={20} />
          </div>
          <Skeleton width={30} height={30} radius={15} />
        </div>
        <div className="body">
          <Skeleton width={132} height={132} radius={10} />
          <div className="grow stack" style={{ gap: 10 }}>
            <Skeleton width="80%" height={30} />
            <Skeleton width="70%" height={30} />
            <Skeleton width="90%" height={40} />
          </div>
        </div>
      </div>
      <Skeleton height={60} radius={14} />
      <div className="grid2">
        <Skeleton height={52} radius={14} />
        <Skeleton height={52} radius={14} />
      </div>
    </SkeletonGroup>
  );
}

/** Déclaration de sinistre : champs du formulaire. */
export function FormSkeleton({ fields = 4 }: { fields?: number }) {
  return (
    <SkeletonGroup className="stack" style={{ gap: 18 }}>
      {Array.from({ length: fields }, (_, i) => (
        <div key={i} className="stack" style={{ gap: 6 }}>
          <Skeleton width={140} height={16} />
          <Skeleton height={52} radius={14} />
        </div>
      ))}
    </SkeletonGroup>
  );
}

/** Profil : identité, langue, apparence, appareils. */
export function ProfileSkeleton() {
  return (
    <SkeletonGroup className="stack" style={{ gap: 14 }}>
      <div className="card">
        <div className="between">
          <Skeleton width={150} height={14} />
          <Skeleton width={90} height={26} radius={14} />
        </div>
        <Skeleton width={120} height={16} />
        <Skeleton height={52} radius={14} />
        <Skeleton width={140} height={16} />
        <Skeleton height={52} radius={14} />
        <Skeleton height={52} radius={14} />
      </div>
      <div className="card">
        <Skeleton width={110} height={14} />
        <Skeleton height={52} radius={14} />
      </div>
      <div className="card">
        <Skeleton width={110} height={14} />
        <Skeleton height={52} radius={14} />
      </div>
    </SkeletonGroup>
  );
}

/** Affichage pour un contrôle : statut, plaque, grand QR, validité. */
export function ControlSkeleton() {
  return (
    <SkeletonGroup className="stack" style={{ alignItems: "center", gap: 20, alignSelf: "stretch" }}>
      <div className="between" style={{ alignSelf: "stretch" }}>
        <Skeleton width={90} height={28} radius={14} />
        <Skeleton width={44} height={44} radius={22} />
      </div>
      <Skeleton width={120} height={14} />
      <Skeleton width={220} height={44} />
      <Skeleton width="min(300px, 80vw)" height="min(300px, 80vw)" radius={16} />
      <div className="grid2" style={{ alignSelf: "stretch" }}>
        <Skeleton height={84} radius={14} />
        <Skeleton height={84} radius={14} />
      </div>
    </SkeletonGroup>
  );
}

/** Lignes d'un tableau de l'espace entreprise. */
export function TableSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <SkeletonGroup className="stack" style={{ gap: 10 }}>
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} height={48} radius={10} />)}
    </SkeletonGroup>
  );
}
