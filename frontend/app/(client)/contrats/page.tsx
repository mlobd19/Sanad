"use client";

import { Icon } from "@/components/Icon";
import { Link } from "@/components/NavLink";
import { ErrorBox, StatusPill } from "@/components/Shell";
import { ContractListSkeleton } from "@/components/Skeletons";
import { type Policy } from "@/lib/api";
import { date, formatPlate, money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useSpace } from "@/lib/spaces";
import { useLoad } from "@/lib/useLoad";

export default function ContractsPage() {
  const { t, lang } = useI18n();
  const { user } = useSpace("customer");
  // Même liste que l'accueil (lib/cache.ts) : affichée tout de suite, puis actualisée.
  const { data: policies, error } = useLoad<Policy[]>("policies", !!user);

  return (
    <main className="content with-nav">
      {error && <ErrorBox message={error} />}
      {!policies && !error && <ContractListSkeleton />}
      {policies && policies.length === 0 && <p className="muted">{t("noContracts")}</p>}
      {policies?.map((p) => (
        <Link key={p.id} href={p.status === "draft" ? `/paiement/${p.id}` : `/contrats/${p.id}`} className="card" style={{ textDecoration: "none", color: "inherit" }}>
          <div className="row">
            <div className="iconbox"><Icon name="car" /></div>
            <div className="grow stack" style={{ gap: 2 }}>
              <strong>{p.product} · <bdi dir="ltr">{formatPlate(p.plate)}</bdi></strong>
              <span className="small muted">{p.insurer} · {money(p.premium, lang)}</span>
            </div>
            <StatusPill status={p.status} />
          </div>
          <span className="small muted">{date(p.starts_on, lang)} → {date(p.ends_on, lang)}</span>
        </Link>
      ))}
      <Link href="/vehicule" className="btn outline block">
        <Icon name="plus" size={18} />
        {t("addVehicle")}
      </Link>
    </main>
  );
}
