"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Icon } from "@/components/Icon";
import { ThemeChoicePicker } from "@/components/ThemeChoice";
import { App, BottomNav, Loading, TopBar } from "@/components/Shell";
import { api, ApiError, type User } from "@/lib/api";
import { displayName, formatPhone } from "@/lib/format";
import { useI18n, type Key, type Lang } from "@/lib/i18n";
import { logout as signOut, useSpace } from "@/lib/spaces";

/** Réponse de la vérification de l'identité numérique (eID Houwiyeti) auprès de l'ANRPTS. */
type IdOutcome = "verified" | "nni_not_found" | "no_eid" | "not_verified";
type IdMessage = { tone: "green" | "sand" | "red"; key: Key };

const OUTCOMES: Record<IdOutcome, IdMessage> = {
  verified: { tone: "green", key: "idVerified" },
  nni_not_found: { tone: "sand", key: "idNniNotFound" },
  no_eid: { tone: "sand", key: "idNoEid" },
  not_verified: { tone: "sand", key: "idNotVerified" }, // message neutre : rien ne dit pourquoi
};

const ID_ERRORS: Record<string, Key> = {
  unavailable: "idUnavailable",
  missing_nni: "idMissing",
  invalid_nni: "idInvalidNni",
  already_verified: "idVerified",
};

export default function ProfilePage() {
  const { t, lang, setLang } = useI18n();
  const router = useRouter();
  const { user, setUser } = useSpace("customer");
  const [nni, setNni] = useState("");
  const [closing, setClosing] = useState(false);
  const [othersMessage, setOthersMessage] = useState("");
  const [checking, setChecking] = useState(false);
  const [idResult, setIdResult] = useState<IdMessage | null>(null);
  // Arrivée depuis l'écran de paiement : on y renvoie une fois l'identité vérifiée.
  const [returnTo, setReturnTo] = useState("");

  useEffect(() => {
    const target = new URLSearchParams(window.location.search).get("retour") ?? "";
    if (/^\/paiement\/\d+$/.test(target)) setReturnTo(target);
  }, []);

  useEffect(() => {
    if (user) setNni(user.nni);
  }, [user]);

  // Un seul champ, le NNI : il est enregistré (un changement relance la vérification), puis l'eID est vérifiée.
  async function checkIdentity(e: FormEvent) {
    e.preventDefault();
    setChecking(true);
    setIdResult(null);
    try {
      if (user && nni !== user.nni) {
        setUser(await api<User>("me", { method: "PATCH", body: { nni } }));
      }
      const r = await api<{ outcome: IdOutcome; user: User }>("me/identity", { method: "POST" });
      setUser(r.user);
      setIdResult(OUTCOMES[r.outcome]);
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      const code = err instanceof ApiError ? err.code : "";
      setIdResult({ tone: "red", key: status === 429 ? "idTooMany" : ID_ERRORS[code] ?? "error" });
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
        <form className="card" onSubmit={checkIdentity} aria-labelledby="kyc-title">
          <div className="between">
            <h2 id="kyc-title" className="eyebrow" style={{ margin: 0 }}>{t("kyc")}</h2>
            <span className={`pill ${user.kyc_status === "verified" ? "" : "warn"}`}>{t(`kyc_${user.kyc_status}` as Key)}</span>
          </div>
          {user.full_name && (
            <div className="field">
              <span className="small muted" id="name-label">{t("idName")}</span>
              <strong aria-labelledby="name-label"><bdi>{displayName(user, lang)}</bdi></strong>
            </div>
          )}
          <div className="field">
            <label htmlFor="phone">{t("phoneLabel")}</label>
            <input id="phone" className="input" value={formatPhone(user.phone)} disabled dir="ltr" />
          </div>
          <div className="field">
            <label htmlFor="nni">{t("nni")}</label>
            <input id="nni" className="input" value={nni} dir="ltr" inputMode="numeric" autoComplete="off" maxLength={10}
              onChange={(e) => setNni(e.target.value.replace(/\D/g, "").slice(0, 10))} aria-describedby="nni-hint" />
            <span id="nni-hint" className="small muted">{user.kyc_status === "verified" ? t("idChangeResets") : t("idCheckHint")}</span>
          </div>
          {(user.kyc_status !== "verified" || nni !== user.nni) && (
            <button className="btn primary block" disabled={checking}>
              {checking ? <span className="spinner sm" aria-hidden="true" /> : <Icon name="shield" size={20} strokeWidth={2} />}
              {checking ? t("idChecking") : t("idCheck")}
            </button>
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
