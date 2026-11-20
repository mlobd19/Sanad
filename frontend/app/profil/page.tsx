"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Icon } from "@/components/Icon";
import { IdentityDocument } from "@/components/IdentityDocument";
import { App, BottomNav, Loading, TopBar, useUser } from "@/components/Shell";
import { api, ApiError, setToken, type User } from "@/lib/api";
import { useI18n, type Key, type Lang } from "@/lib/i18n";

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
  const { user, setUser } = useUser();
  const [fullName, setFullName] = useState("");
  const [nni, setNni] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
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
    setToken(null);
    router.replace("/connexion");
  }

  if (!user) return <App><Loading /></App>;

  return (
    <App>
      <TopBar title={t("profileTitle")} />
      <main className="content with-nav">
        <form className="card" onSubmit={save}>
          <div className="field">
            <label htmlFor="phone">{t("phoneLabel")}</label>
            <input id="phone" className="input" value={user.phone} disabled dir="ltr" />
          </div>
          <div className="field">
            <label htmlFor="name">{t("fullName")}</label>
            <input id="name" className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="name" />
          </div>
          <div className="field">
            <label htmlFor="nni">{t("nni")}</label>
            <input id="nni" className="input" value={nni} onChange={(e) => setNni(e.target.value)} inputMode="numeric" dir="ltr" />
          </div>
          <div className="between">
            <span className="muted">{t("kyc")}</span>
            <span className={`pill ${user.kyc_status === "verified" ? "" : user.kyc_status === "rejected" ? "bad" : "warn"}`}>
              {t(`kyc_${user.kyc_status}` as Key)}
            </span>
          </div>
          {user.kyc_status === "verified" && <span className="small muted">{t("idChangeResets")}</span>}
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
          {returnTo && user.kyc_status === "verified" && (
            <Link className="btn primary block" href={returnTo}>{t("continueToPay")}</Link>
          )}
          {(user.kyc_status === "none" || user.kyc_status === "pending") && (
            <IdentityDocument user={user} onUploaded={setUser}
              open={!registry || (idResult !== null && idResult.key !== "idMatch")} />
          )}
          <div aria-live="polite">
            {idResult && (
              <p className={`banner ${idResult.tone}`} role={idResult.tone === "red" ? "alert" : "status"} style={{ margin: 0 }}>
                {t(idResult.key)}
              </p>
            )}
          </div>
          {message && <p className="small" role="status" style={{ margin: 0 }}>{message}</p>}
          <button className="btn primary block" disabled={busy}>{t("save")}</button>
        </form>

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

        <button type="button" className="btn outline block" onClick={logout}>{t("logout")}</button>
      </main>
      <BottomNav />
    </App>
  );
}
