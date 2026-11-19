"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Icon } from "@/components/Icon";
import { InsurerLogo } from "@/components/InsurerLogo";
import { Wordmark } from "@/components/Logo";
import { App, BottomNav, ErrorBox, Loading, StatusPill, useUser } from "@/components/Shell";
import { api, type Policy } from "@/lib/api";
import { addDays, date, daysUntil } from "@/lib/format";
import { useI18n, type Key } from "@/lib/i18n";

const SERVICES: { key: Key; icon: string; on: boolean }[] = [
  { key: "auto", icon: "car", on: true },
  { key: "health", icon: "heart", on: false },
  { key: "home", icon: "home", on: false },
  { key: "travel", icon: "plane", on: false },
  { key: "takaful", icon: "shield", on: false },
  { key: "pro", icon: "briefcase", on: false },
];

function ContractCard({ p, raised }: { p: Policy; raised?: boolean }) {
  const { t, lang } = useI18n();
  const days = daysUntil(p.ends_on);
  const renew = p.status === "active" && !p.renewed && days <= 30;
  return (
    <div className={`card${raised ? " raised" : ""}`}>
      <div className="row">
        {p.insurer_logo ? (
          <InsurerLogo name={p.insurer} logo={p.insurer_logo} size={48} />
        ) : (
          <div className="iconbox"><Icon name="car" size={24} strokeWidth={2} /></div>
        )}
        <div className="grow stack" style={{ gap: 2 }}>
          <span className="plate"><bdi>{p.plate}</bdi></span>
          <span className="ink2" style={{ fontSize: 14 }}>{p.insurer} · {p.product}</span>
        </div>
        <StatusPill status={p.status} />
      </div>
      {renew && (
        <div className="banner sand">
          <Icon name="clock" size={20} strokeWidth={2} />
          <span className="grow" style={{ fontWeight: 600, fontSize: 14 }}>{t("expiresShort", { date: date(p.ends_on, lang) })}</span>
          <Link href={`/devis/${p.asset_id}?renouvellement=${p.id}&debut=${addDays(p.ends_on, 1)}`}>{t("renew")}</Link>
        </div>
      )}
      {p.status === "draft" ? (
        <Link className="btn primary block" href={`/paiement/${p.id}`}>{t("payTitle")}</Link>
      ) : p.attestation ? (
        <Link className="btn dark block" href={`/contrats/${p.id}/controle`}>
          <Icon name="qr" size={20} strokeWidth={2} />
          {t("showAttestation")}
        </Link>
      ) : (
        <Link className="btn outline block" href={`/contrats/${p.id}`}>{t("seeDetails")}</Link>
      )}
    </div>
  );
}

export default function HomePage() {
  const { t, lang, setLang } = useI18n();
  const { user } = useUser();
  const [policies, setPolicies] = useState<Policy[] | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setError("");
    api<Policy[]>("policies").then(setPolicies).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  if (!user || (!policies && !error)) return <App><Loading /></App>;

  const current = (policies ?? []).filter((p) => ["active", "paid", "draft"].includes(p.status));
  const active = current.filter((p) => p.status === "active");
  const nextEnd = active.filter((p) => !p.renewed).map((p) => daysUntil(p.ends_on)).sort((a, b) => a - b)[0];
  const firstName = user.full_name.split(" ")[0];

  return (
    <App>
      <header className="hero">
        <div className="between">
          <Wordmark name={t("appName")} size={17} onDark />
          <button type="button" className="btn-on-dark" onClick={() => setLang(lang === "fr" ? "ar" : "fr")} aria-label={t("language")}>
            FR · ع
          </button>
        </div>
        <div className="stack" style={{ gap: 4 }}>
          <h1>{firstName ? t("helloName", { name: `⁨${firstName}⁩` }) : t("hello")}</h1>
          {active.length > 0 && (
            <span className="sub">
              {t("activeCount", { count: active.length })}
              {nextEnd !== undefined && nextEnd <= 30 ? ` · ${t("renewIn", { days: Math.max(nextEnd, 0) })}` : ""}
            </span>
          )}
        </div>
      </header>

      <main className="content with-nav overlap">
        {error && <ErrorBox message={error} onRetry={load} />}

        {current.length === 0 ? (
          <div className="card raised">
            <p style={{ margin: 0, fontSize: 16 }}>{t("noContracts")}</p>
            <Link href="/vehicule" className="btn primary block">{t("seeQuotes")}</Link>
          </div>
        ) : (
          current.map((p, i) => <ContractCard key={p.id} p={p} raised={i === 0} />)
        )}

        <section className="stack">
          <h2 className="eyebrow">{t("subscribe")}</h2>
          <div className="grid3">
            {SERVICES.map((s) =>
              s.on ? (
                <Link key={s.key} href="/vehicule" className="tile on">
                  <Icon name={s.icon} size={26} strokeWidth={2} />
                  <strong>{t(s.key)}</strong>
                  <span className="state">{t("available")}</span>
                </Link>
              ) : (
                <div key={s.key} className="tile" aria-disabled="true">
                  <Icon name={s.icon} size={26} strokeWidth={2} />
                  <strong>{t(s.key)}</strong>
                  <span className="state">{t("soon")}</span>
                </div>
              ),
            )}
          </div>
        </section>
      </main>
      <BottomNav />
    </App>
  );
}
