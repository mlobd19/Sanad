"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useRef, useState, type KeyboardEvent } from "react";

import { Wordmark } from "@/components/Logo";
import { ThemeIconButton } from "@/components/ThemeChoice";
import { OtpLogin, type OtpResult } from "@/components/OtpLogin";
import { ProLoginForm } from "@/components/ProAuth";
import { api, setToken } from "@/lib/api";
import { useI18n, type Key } from "@/lib/i18n";
import { enterSpace, useRedirectIfLoggedIn, type LoginTab } from "@/lib/spaces";

const TABS: { id: LoginTab; label: Key }[] = [
  { id: "particulier", label: "tabPersonal" },
  { id: "pro", label: "tabPro" },
];

/** Page de connexion unique : particuliers (téléphone + SMS) et professionnels (email + mot de passe + SMS). */
export default function LoginPage() {
  return (
    <Suspense fallback={<div className="app" style={{ background: "var(--green-deep)" }} />}>
      <Login />
    </Suspense>
  );
}

function Login() {
  const { t, lang, setLang } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const [tab, setTab] = useState<LoginTab>(params.get("espace") === "pro" ? "pro" : "particulier");
  const tabRefs = useRef<Record<LoginTab, HTMLButtonElement | null>>({ particulier: null, pro: null });
  const state = useRedirectIfLoggedIn(); // déjà connecté → directement dans son espace

  function select(next: LoginTab) {
    setTab(next);
    // L'adresse garde l'onglet : un rechargement ou un lien partagé rouvre le même.
    router.replace(next === "pro" ? "/connexion?espace=pro" : "/connexion", { scroll: false });
  }

  function onTabKey(e: KeyboardEvent<HTMLButtonElement>) {
    const step = { ArrowRight: 1, ArrowLeft: -1, Home: -9, End: 9 }[e.key];
    if (!step) return;
    e.preventDefault();
    const rtl = document.documentElement.dir === "rtl";
    const i = TABS.findIndex((x) => x.id === tab);
    const j = Math.abs(step) === 9 ? (step > 0 ? TABS.length - 1 : 0) : (i + (rtl ? -step : step) + TABS.length) % TABS.length;
    select(TABS[j].id);
    tabRefs.current[TABS[j].id]?.focus();
  }

  async function onVerified({ token, user }: OtpResult) {
    setToken(token);
    if (user.language !== lang) await api("me", { method: "PATCH", body: { language: lang } });
    enterSpace(router, user);
  }

  return (
    <div className="app" style={{ background: "var(--green-deep)" }}>
      <div style={{ padding: "28px 24px 32px", display: "flex", flexDirection: "column", gap: 28, color: "#fff" }}>
        <div className="between">
          <Link href="/" aria-label={t("appName")} style={{ color: "#fff", textDecoration: "none" }}>
            <Wordmark name={t("appName")} size={22} onDark />
          </Link>
          <div className="head-actions">
            <button type="button" className="btn-on-dark" onClick={() => setLang(lang === "fr" ? "ar" : "fr")}>
              {lang === "fr" ? "العربية" : "Français"}
            </button>
            <ThemeIconButton />
          </div>
        </div>
        <h1 className="title" style={{ fontSize: 34, lineHeight: 1.12, color: "#fff" }}>{t("tagline")}</h1>
      </div>

      <main className="sheet">
        {state === "checking" ? (
          <div className="center" style={{ minHeight: 240 }}><span className="spinner" aria-label={t("loading")} /></div>
        ) : (
          <>
            <div className="login-tabs" role="tablist" aria-label={t("loginSpaceLabel")}>
              {TABS.map(({ id, label }) => (
                <button
                  key={id}
                  ref={(el) => { tabRefs.current[id] = el; }}
                  type="button"
                  role="tab"
                  id={`login-tab-${id}`}
                  aria-selected={tab === id}
                  aria-controls={`login-panel-${id}`}
                  tabIndex={tab === id ? 0 : -1}
                  onClick={() => select(id)}
                  onKeyDown={onTabKey}
                >
                  {t(label)}
                </button>
              ))}
            </div>
            <div role="tabpanel" id={`login-panel-${tab}`} aria-labelledby={`login-tab-${tab}`}
              className="stack" style={{ gap: 0, flex: 1 }}>
              {tab === "particulier" ? (
                <OtpLogin key="particulier" title={t("loginTitle")} intro={t("loginIntro")} onVerified={onVerified} />
              ) : (
                <ProLoginForm
                  key="pro"
                  titleKey="proLoginTitle"
                  introKey="proLoginIntro"
                  footer={
                    <p className="small ink2" style={{ margin: 0, textAlign: "center" }}>
                      {t("companyNoAccount")}{" "}
                      <Link href="/entreprise/inscription" style={{ fontWeight: 700 }}>{t("createCompanyAccount")}</Link>
                    </p>
                  }
                />
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
