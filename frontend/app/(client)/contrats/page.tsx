"use client";

import { useState } from "react";

import { Icon } from "@/components/Icon";
import { Link } from "@/components/NavLink";
import { ErrorBox, StatusPill } from "@/components/Shell";
import { ContractListSkeleton } from "@/components/Skeletons";
import { type Branch, type Policy } from "@/lib/api";
import { destinationsLabel } from "@/lib/countries";
import { date, formatPlate, money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useSpace } from "@/lib/spaces";
import { useLoad } from "@/lib/useLoad";

export default function ContractsPage() {
  const { t, lang } = useI18n();
  const { user } = useSpace("customer");
  // Même liste que l'accueil (lib/cache.ts) : affichée tout de suite, puis actualisée.
  const { data: policies, error } = useLoad<Policy[]>("policies", !!user);
  const [branch, setBranch] = useState<Branch | "all">("all");
  const shown = (policies ?? []).filter((p) => branch === "all" || p.branch === branch);
  // Filtre par produit dès que les deux produits sont présents.
  const both = new Set((policies ?? []).map((p) => p.branch)).size > 1;

  return (
    <main className="content with-nav">
      {error && <ErrorBox message={error} />}
      {!policies && !error && <ContractListSkeleton />}
      {policies && policies.length === 0 && <p className="muted">{t("noContracts")}</p>}
      {both && (
        <div className="chips" role="group" aria-label={t("filterProducts")}>
          {(["all", "auto", "travel"] as const).map((b) => (
            <button key={b} type="button" aria-pressed={branch === b} onClick={() => setBranch(b)}>
              {t(b === "all" ? "filterAll" : b)}
            </button>
          ))}
        </div>
      )}
      {shown.map((p) => (
        <Link key={p.id} href={p.status === "draft" ? `/paiement/${p.id}` : `/contrats/${p.id}`} className="card" style={{ textDecoration: "none", color: "inherit" }}>
          <div className="row">
            <div className="iconbox"><Icon name={p.trip ? "plane" : "car"} /></div>
            <div className="grow stack" style={{ gap: 2, minWidth: 0 }}>
              {p.trip ? (
                <strong>{p.product} · {destinationsLabel(p.trip.destinations, lang, 2)}</strong>
              ) : (
                <strong>{p.product} · <bdi dir="ltr">{formatPlate(p.plate)}</bdi></strong>
              )}
              <span className="small muted">
                {p.insurer} · {money(p.premium, lang)}
                {p.trip && <> · {t("travelersCount", { count: p.trip.travelers.length })}</>}
              </span>
            </div>
            <StatusPill status={p.status} />
          </div>
          <span className="small muted">{date(p.starts_on, lang)} → {date(p.ends_on, lang)}</span>
        </Link>
      ))}
    </main>
  );
}
