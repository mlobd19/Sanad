"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Icon } from "@/components/Icon";
import { InsurerLogo } from "@/components/InsurerLogo";
import { KhaimaMark, Wordmark } from "@/components/Logo";
import { App, BottomNav, ErrorBox, Loading, StatusPill } from "@/components/Shell";
import { api, type Policy } from "@/lib/api";
import { addDays, date, daysUntil } from "@/lib/format";
import { useI18n, type Key } from "@/lib/i18n";
import { useHasToken, useSpace } from "@/lib/spaces";

const SERVICES: { key: Key; icon: string; on: boolean }[] = [
  { key: "auto", icon: "car", on: true },
  { key: "health", icon: "heart", on: false },
  { key: "home", icon: "home", on: false },
  { key: "travel", icon: "plane", on: false },
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
          <Link href={`/devis/${p.asset_id}?renouvellement=${p.id}&debut=${addDays(p.ends_on, 1)}&duree=${p.duration_months}`}>{t("renew")}</Link>
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

/** Visiteur non connecté : page d'accueil et choix de l'espace. Connecté : l'accueil client
 *  (un compte d'un autre rôle est renvoyé vers son espace par useSpace). */
export default function HomePage() {
  const hasToken = useHasToken();
  if (hasToken === null) return <App><Loading /></App>;
  return hasToken ? <CustomerHome /> : <Landing />;
}

function Landing() {
  const { t, lang, setLang } = useI18n();
  const entries: { href: string; icon: string; title: Key; hint: Key }[] = [
    { href: "/connexion", icon: "user", title: "entryPersonal", hint: "entryPersonalHint" },
    { href: "/connexion?espace=pro", icon: "briefcase", title: "entryCompany", hint: "entryCompanyHint" },
    { href: "/connexion?espace=pro", icon: "shield", title: "entryInsurer", hint: "entryInsurerHint" },
  ];
  return (
    <div className="app" style={{ background: "var(--green-deep)" }}>
      <header style={{ padding: "24px 24px 32px", display: "flex", flexDirection: "column", gap: 24, color: "#fff" }}>
        <div className="between">
          <Wordmark name={t("appName")} size={22} onDark />
          <button type="button" className="btn-on-dark" onClick={() => setLang(lang === "fr" ? "ar" : "fr")}>
            {lang === "fr" ? "العربية" : "Français"}
          </button>
        </div>
        <KhaimaMark size={84} color="#fff" />
        <div className="stack" style={{ gap: 10 }}>
          <h1 className="title" style={{ fontSize: 34, lineHeight: 1.12, color: "#fff" }}>{t("tagline")}</h1>
          <p style={{ margin: 0, color: "var(--green-soft)", fontSize: 16, lineHeight: 1.5 }}>{t("landingIntro")}</p>
        </div>
      </header>

      <main className="sheet" style={{ gap: 14 }}>
        <h2 className="eyebrow" style={{ margin: 0 }}>{t("landingChoose")}</h2>
        <nav aria-label={t("loginSpaceLabel")} className="stack" style={{ gap: 12 }}>
          {entries.map((e) => (
            <Link key={e.title} href={e.href} className="entry">
              <span className="iconbox" aria-hidden="true"><Icon name={e.icon} size={24} strokeWidth={2} /></span>
              <span>
                <strong>{t(e.title)}</strong>
                <span className="hint">{t(e.hint)}</span>
              </span>
              <span className="chev" aria-hidden="true"><Icon name="back" size={22} strokeWidth={2.4} /></span>
            </Link>
          ))}
        </nav>
        <p className="small ink2" style={{ margin: 0, textAlign: "center" }}>
          {t("companyNoAccount")} <Link href="/entreprise/inscription" style={{ fontWeight: 700 }}>{t("createCompanyAccount")}</Link>
        </p>
        <div className="grow" />
        {/* Back-office Django : lien simple (pas le routeur Next.js). */}
        <a href="/admin/" className="staff-link">{t("staffEntry")}</a>
      </main>
    </div>
  );
}

function CustomerHome() {
  const { t, lang, setLang } = useI18n();
  const { user } = useSpace("customer");
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
          <div className="grid2">
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
