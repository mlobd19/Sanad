"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Icon } from "@/components/Icon";
import { App, BottomNav, ErrorBox, Loading, StatusPill, TopBar, useUser } from "@/components/Shell";
import { api, type Policy } from "@/lib/api";
import { date, money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

export default function ContractsPage() {
  const { t, lang } = useI18n();
  const { user } = useUser();
  const [policies, setPolicies] = useState<Policy[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (user) api<Policy[]>("policies").then(setPolicies).catch((e) => setError(e.message));
  }, [user]);

  return (
    <App>
      <TopBar title={t("myContracts")} />
      <main className="content with-nav">
        {error && <ErrorBox message={error} />}
        {!policies && !error && <Loading />}
        {policies && policies.length === 0 && <p className="muted">{t("noContracts")}</p>}
        {policies?.map((p) => (
          <Link key={p.id} href={p.status === "draft" ? `/paiement/${p.id}` : `/contrats/${p.id}`} className="card" style={{ textDecoration: "none", color: "inherit" }}>
            <div className="row">
              <div className="iconbox"><Icon name="car" /></div>
              <div className="grow stack" style={{ gap: 2 }}>
                <strong>{p.product} · <bdi>{p.plate}</bdi></strong>
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
      <BottomNav />
    </App>
  );
}
