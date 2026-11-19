"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { App, BottomNav, Loading, TopBar, useUser } from "@/components/Shell";
import { api, ApiError, setToken, type User } from "@/lib/api";
import { useI18n, type Key, type Lang } from "@/lib/i18n";

export default function ProfilePage() {
  const { t, lang, setLang } = useI18n();
  const router = useRouter();
  const { user, setUser } = useUser();
  const [fullName, setFullName] = useState("");
  const [nni, setNni] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

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
