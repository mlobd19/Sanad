"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Icon } from "@/components/Icon";
import { KhaimaMark } from "@/components/Logo";
import { App, BottomNav, ErrorBox, Loading, StatusPill, useUser } from "@/components/Shell";
import { api, type Policy } from "@/lib/api";
import { addDays, date, daysUntil, money } from "@/lib/format";
import { useI18n, type Key } from "@/lib/i18n";

const SERVICES: { key: Key; icon: string; on: boolean }[] = [
  { key: "auto", icon: "car", on: true },
  { key: "health", icon: "heart", on: false },
  { key: "home", icon: "home", on: false },
  { key: "travel", icon: "plane", on: false },
  { key: "takaful", icon: "shield", on: false },
  { key: "pro", icon: "briefcase", on: false },
];

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
  const toRenew = current.find((p) => p.status === "active" && !p.renewed && daysUntil(p.ends_on) <= 30);

  return (
    <App>
      <main className="content with-nav">
        <div className="between" style={{ alignItems: "center" }}>
          <div className="stack" style={{ gap: 2 }}>
            <span className="wordmark" style={{ fontSize: 15, color: "var(--green)" }}>
              <KhaimaMark size={22} />
              {t("appName")}
            </span>
            <h1 className="title">{user.full_name ? t("helloName", { name: `\u2068${user.full_name.split(" ")[0]}\u2069` }) : t("hello")}</h1>
          </div>
          <button type="button" className="btn outline" onClick={() => setLang(lang === "fr" ? "ar" : "fr")} aria-label={t("language")}>
            FR · ع
          </button>
        </div>

        {error && <ErrorBox message={error} onRetry={load} />}

        {toRenew && (
          <div className="banner sand">
            <div className="grow stack" style={{ gap: 2 }}>
              <strong>{t("renewTitle", { days: Math.max(daysUntil(toRenew.ends_on), 0) })}</strong>
              <span className="small">{t("renewText")}</span>
            </div>
            <Link
              className="btn dark"
              href={`/devis/${toRenew.asset_id}?renouvellement=${toRenew.id}&debut=${addDays(toRenew.ends_on, 1)}`}
            >
              {t("renew")}
            </Link>
          </div>
        )}

        <section className="stack">
          <h2 className="eyebrow">{t("myContracts")}</h2>
          {current.length === 0 && <p className="muted" style={{ margin: 0 }}>{t("noContracts")}</p>}
          {current.map((p) => (
            <div key={p.id} className="card">
              <div className="row">
                <div className="iconbox"><Icon name="car" /></div>
                <div className="grow stack" style={{ gap: 2 }}>
                  <strong>{t("auto")} · {p.product}</strong>
                  <span className="small muted">{p.insurer} · <bdi>{p.plate}</bdi></span>
                </div>
                <StatusPill status={p.status} />
              </div>
              <div className="between small muted">
                <span>{t("expiresOn", { date: date(p.ends_on, lang) })}</span>
                <span>{t("premiumPerYear", { amount: money(p.premium, lang) })}</span>
              </div>
              {p.status === "draft" ? (
                <Link className="btn outline block" href={`/paiement/${p.id}`}>{t("payTitle")}</Link>
              ) : (
                <Link className="btn outline block" href={`/contrats/${p.id}`} style={{ color: "var(--green)", borderColor: "var(--green)" }}>
                  {p.attestation ? t("seeAttestation") : t("seeDetails")}
                </Link>
              )}
            </div>
          ))}
        </section>

        <section className="stack">
          <h2 className="eyebrow">{t("subscribe")}</h2>
          <div className="grid3">
            {SERVICES.map((s) =>
              s.on ? (
                <Link key={s.key} href="/vehicule" className="tile on">
                  <span className="ico"><Icon name={s.icon} size={24} /></span>
                  <strong>{t(s.key)}</strong>
                  <span className="state">{t("available")}</span>
                </Link>
              ) : (
                <div key={s.key} className="tile" aria-disabled="true">
                  <span className="ico"><Icon name={s.icon} size={24} /></span>
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
