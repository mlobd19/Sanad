"use client";

import { useEffect, useState } from "react";

import { Icon } from "@/components/Icon";
import { InsurerLogo } from "@/components/InsurerLogo";
import { StackedLogo, Wordmark } from "@/components/Logo";
import { ThemeIconButton } from "@/components/ThemeChoice";
import { VehicleIllustration } from "@/components/VehicleIllustration";
import { Link } from "@/components/NavLink";
import { ErrorBox, Skeleton, StatusPill } from "@/components/Shell";
import { HomeContractsSkeleton } from "@/components/Skeletons";
import { LanguageButton } from "@/components/LanguageButton";
import { type Policy } from "@/lib/api";
import { addDays, date, daysUntil, displayName, formatPlate } from "@/lib/format";
import { useI18n, type Key } from "@/lib/i18n";
import { useHasToken, useSpace } from "@/lib/spaces";
import { prefetch, useLoad } from "@/lib/useLoad";

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
      <div className="row" style={{ alignItems: "center" }}>
        <VehicleIllustration type={p.body_type} width={108} />
        <div className="grow stack" style={{ gap: 4, minWidth: 0 }}>
          <span className="plate"><bdi dir="ltr">{formatPlate(p.plate)}</bdi></span>
          <span className="row ink2" style={{ fontSize: 14, gap: 6 }}>
            <InsurerLogo name={p.insurer} logo={p.insurer_logo} size={24} />
            <span>{p.insurer} · {p.product}</span>
          </span>
          <span><StatusPill status={p.status} /></span>
        </div>
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
  // Le navigateur n'est pas encore lu : l'en-tête vert, commun aux deux pages.
  if (hasToken === null) return <header className="hero" style={{ flex: 1 }} aria-busy="true" />;
  return hasToken ? <CustomerHome /> : <Landing />;
}

function Landing() {
  const { t } = useI18n();
  const entries: { href: string; icon: string; title: Key; hint: Key }[] = [
    { href: "/connexion", icon: "user", title: "entryPersonal", hint: "entryPersonalHint" },
    { href: "/connexion?espace=pro", icon: "briefcase", title: "entryCompany", hint: "entryCompanyHint" },
    { href: "/connexion?espace=pro", icon: "shield", title: "entryInsurer", hint: "entryInsurerHint" },
  ];
  return (
    <div className="landing">
      <header style={{ padding: "24px 24px 32px", display: "flex", flexDirection: "column", gap: 24, color: "#fff" }}>
        <div className="head-actions" style={{ justifyContent: "flex-end" }}>
          <LanguageButton />
          <ThemeIconButton />
        </div>
        <div style={{ alignSelf: "center" }}>
          <StackedLogo size={84} onDark />
        </div>
        <div className="stack" style={{ gap: 10 }}>
          <h1 className="title" style={{ fontSize: 34, lineHeight: 1.12, color: "#fff" }}>{t("tagline")}</h1>
          <p style={{ margin: 0, color: "var(--on-deep)", fontSize: 16, lineHeight: 1.5 }}>{t("landingIntro")}</p>
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

/** « Bonsoir » de 19 h à 5 h (heure du téléphone), « Bonjour » le reste de la journée. */
const EVENING_FROM = 19;
const MORNING_FROM = 5;

function isEvening(now: Date = new Date()): boolean {
  const hour = now.getHours();
  return hour >= EVENING_FROM || hour < MORNING_FROM;
}

/** Suit l'heure : la salutation change d'elle-même si l'écran reste ouvert à 19 h ou à 5 h. */
function useEvening(): boolean {
  const [evening, setEvening] = useState(false);
  useEffect(() => {
    const update = () => setEvening(isEvening());
    update();
    const id = setInterval(update, 60_000);
    return () => clearInterval(id);
  }, []);
  return evening;
}

function CustomerHome() {
  const { t, lang } = useI18n();
  const evening = useEvening();
  const { user } = useSpace("customer");
  // Dernière liste connue tout de suite (lib/cache.ts), actualisée une fois le compte confirmé.
  const { data: policies, error, reload } = useLoad<Policy[]>("policies", !!user);
  // Écran suivant le plus probable : la liste des véhicules est prête avant d'y aller.
  useEffect(() => {
    if (user) prefetch("assets");
  }, [user]);

  const current = (policies ?? []).filter((p) => ["active", "paid", "draft"].includes(p.status));
  const active = current.filter((p) => p.status === "active");
  const nextEnd = active.filter((p) => !p.renewed).map((p) => daysUntil(p.ends_on)).sort((a, b) => a - b)[0];
  const firstName = user ? displayName(user, lang).split(" ")[0] : "";

  return (
    <>
      <header className="hero">
        <div className="between">
          <Wordmark name={t("appName")} size={17} onDark />
          <div className="head-actions">
            <LanguageButton />
            <ThemeIconButton />
          </div>
        </div>
        <div className="stack" style={{ gap: 4 }}>
          {user ? (
            <h1>{firstName ? t(evening ? "eveningName" : "helloName", { name: `⁨${firstName}⁩` }) : t(evening ? "evening" : "hello")}</h1>
          ) : (
            <Skeleton width={190} height={34} style={{ opacity: 0.25 }} />
          )}
          {!policies && <Skeleton width={150} height={18} style={{ opacity: 0.25 }} />}
          {active.length > 0 && (
            <span className="sub">
              {t("activeCount", { count: active.length })}
              {nextEnd !== undefined && nextEnd <= 30 ? ` · ${t("renewIn", { days: Math.max(nextEnd, 0) })}` : ""}
            </span>
          )}
        </div>
      </header>

      <main className="content with-nav overlap">
        {error && <ErrorBox message={error} onRetry={reload} />}

        {!policies && !error ? (
          <HomeContractsSkeleton />
        ) : (
          <>
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
          </>
        )}
      </main>
    </>
  );
}
