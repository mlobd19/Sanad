"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Icon } from "@/components/Icon";
import { IdentityDocument } from "@/components/IdentityDocument";
import { ThemeChoicePicker } from "@/components/ThemeChoice";
import { App, BottomNav, Loading, TopBar } from "@/components/Shell";
import { api, ApiError, type User } from "@/lib/api";
import { formatPhone } from "@/lib/format";
import { useI18n, type Key, type Lang } from "@/lib/i18n";
import { logout as signOut, useSpace } from "@/lib/spaces";

type IdOutcome = "match" | "mismatch" | "not_found";

const OUTCOMES: Record<IdOutcome, { tone: "green" | "sand"; key: Key }> = {
  match: { tone: "green", key: "idMatch" },
  mismatch: { tone: "sand", key: "idMismatch" },
  not_found: { tone: "sand", key: "idNotFound" },
};

const ID_ERRORS: Record<string, Key> = {
  unavailable: "idUnavailable",
  missing_fields: "idMissing",
  invalid_nni: "idInvalidNni",
  rejected: "idRejected",
  already_verified: "idMatch",
};

export default function ProfilePage() {
  const { t, lang, setLang } = useI18n();
  const router = useRouter();
  const { user, setUser } = useSpace("customer");
  const [fullName, setFullName] = useState("");
  const [nni, setNni] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [closing, setClosing] = useState(false);
  const [othersMessage, setOthersMessage] = useState("");
  const [registry, setRegistry] = useState(false);
  const [checking, setChecking] = useState(false);
  const [idResult, setIdResult] = useState<{ tone: "green" | "sand" | "red"; key: Key } | null>(null);
  // Arrivée depuis l'écran de paiement : on y renvoie une fois l'identité vérifiée.
  const [returnTo, setReturnTo] = useState("");

  useEffect(() => {
    const target = new URLSearchParams(window.location.search).get("retour") ?? "";
    if (/^\/paiement\/\d+$/.test(target)) setReturnTo(target);
  }, []);

  useEffect(() => {
    api<{ available: boolean }>("me/identity").then((r) => setRegistry(r.available)).catch(() => setRegistry(false));
  }, []);

  useEffect(() => {
    if (user) {
      setFullName(user.full_name);
      setNni(user.nni);
    }
  }, [user]);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      setUser(await api<User>("me", { method: "PATCH", body: { full_name: fullName, nni, language: lang } }));
      setMessage(t("saved"));
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : t("error"));
    } finally {
      setBusy(false);
    }
  }

  // Vérification au registre national : enregistre d'abord le nom et le NNI saisis, puis interroge le registre.
  async function checkIdentity() {
    setChecking(true);
    setIdResult(null);
    setMessage("");
    try {
      if (user && (fullName !== user.full_name || nni !== user.nni)) {
        setUser(await api<User>("me", { method: "PATCH", body: { full_name: fullName, nni } }));
      }
      const r = await api<{ outcome: IdOutcome; user: User }>("me/identity", { method: "POST" });
      setUser(r.user);
      setIdResult(OUTCOMES[r.outcome]);
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "";
      setIdResult({ tone: "red", key: ID_ERRORS[code] ?? (err instanceof ApiError && err.status === 429 ? "idUnavailable" : "error") });
    } finally {
      setChecking(false);
    }
  }

  function changeLang(l: Lang) {
    setLang(l);
    api("me", { method: "PATCH", body: { language: l } }).catch(() => undefined);
  }

  function logout() {
    signOut(router);
  }

  // Ferme les connexions des autres téléphones et ordinateurs ; celle-ci reste ouverte.
  async function logoutOthers() {
    setClosing(true);
    setOthersMessage("");
    try {
      const r = await api<{ closed: number }>("auth/logout-others", { method: "POST" });
      setOthersMessage(r.closed > 0 ? t("logoutOthersDone", { n: r.closed }) : t("logoutOthersNone"));
    } catch {
      setOthersMessage(t("error"));
    } finally {
      setClosing(false);
    }
  }

  if (!user) return <App><Loading /></App>;

  return (
    <App>
      <TopBar title={t("profileTitle")} />
      <main className="content with-nav">
        <form className="card" onSubmit={save}>
          <div className="field">
            <label htmlFor="phone">{t("phoneLabel")}</label>
            <input id="phone" className="input" value={formatPhone(user.phone)} disabled dir="ltr" />
          </div>
          <div className="field">
            <label htmlFor="name">{t("fullName")}</label>
            <input id="name" className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="name" />
          </div>
          <div className="field">
            <label htmlFor="nni">{t("nni")}</label>
            <input id="nni" className="input" value={nni} onChange={(e) => setNni(e.target.value)} inputMode="numeric" dir="ltr" />
          </div>
          {user.kyc_status === "verified" && <span className="small muted">{t("idChangeResets")}</span>}
          {message && <p className="small" role="status" style={{ margin: 0 }}>{message}</p>}
          <button className="btn primary block" disabled={busy}>{t("save")}</button>
        </form>

        {/* Hors du formulaire du profil : le dépôt de pièce a son propre formulaire (pas de <form> imbriqués). */}
        <section className="card" aria-labelledby="kyc-title">
          <div className="between">
            <h2 id="kyc-title" className="eyebrow" style={{ margin: 0 }}>{t("kyc")}</h2>
            <span className={`pill ${user.kyc_status === "verified" ? "" : user.kyc_status === "rejected" ? "bad" : "warn"}`}>
              {t(`kyc_${user.kyc_status}` as Key)}
            </span>
          </div>
          {registry && (user.kyc_status === "none" || user.kyc_status === "pending") && (
            <div className="stack" style={{ gap: 6 }}>
              <button type="button" className="btn outline block" onClick={checkIdentity} disabled={checking || busy}
                aria-describedby="id-hint">
                {checking ? <span className="spinner sm" aria-hidden="true" /> : <Icon name="shield" size={20} strokeWidth={2} />}
                {checking ? t("idChecking") : t("idCheck")}
              </button>
              <span id="id-hint" className="small muted">{t("idCheckHint")}</span>
            </div>
          )}
          <div aria-live="polite">
            {idResult && (
              <p className={`banner ${idResult.tone}`} role={idResult.tone === "red" ? "alert" : "status"} style={{ margin: 0 }}>
                {t(idResult.key)}
              </p>
            )}
          </div>
          {returnTo && user.kyc_status === "verified" && (
            <Link className="btn primary block" href={returnTo}>{t("continueToPay")}</Link>
          )}
          {(user.kyc_status === "none" || user.kyc_status === "pending") && (
            <IdentityDocument user={user} onUploaded={setUser}
              open={!registry || (idResult !== null && idResult.key !== "idMatch")} />
          )}
        </section>

        <section className="card">
          <h2 className="eyebrow">{t("language")}</h2>
          <div className="segmented" style={{ gridTemplateColumns: "1fr 1fr" }} role="radiogroup">
            {(["fr", "ar"] as const).map((l) => (
              <button key={l} type="button" role="radio" aria-checked={lang === l} className="radio" style={{ justifyContent: "center", minHeight: 48 }} onClick={() => changeLang(l)}>
                {l === "fr" ? "Français" : "العربية"}
              </button>
            ))}
          </div>
        </section>

        <section className="card" aria-labelledby="theme-title">
          <h2 id="theme-title" className="eyebrow">{t("theme")}</h2>
          <ThemeChoicePicker />
        </section>

        <section className="card" aria-labelledby="devices-title">
          <h2 id="devices-title" className="eyebrow">{t("devicesTitle")}</h2>
          <p className="small ink2" style={{ margin: 0 }}>{t("devicesHint")}</p>
          <button type="button" className="btn outline block" onClick={logoutOthers} disabled={closing}>
            {closing ? <span className="spinner sm" aria-hidden="true" /> : null}
            {t("logoutOthers")}
          </button>
          <div aria-live="polite">
            {othersMessage && <p className="small" role="status" style={{ margin: 0 }}>{othersMessage}</p>}
          </div>
        </section>

        <button type="button" className="btn outline block" onClick={logout}>{t("logout")}</button>
      </main>
      <BottomNav />
    </App>
  );
}
