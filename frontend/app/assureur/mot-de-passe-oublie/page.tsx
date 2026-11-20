"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { PortalAuthShell } from "@/components/PortalAuthShell";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function ForgotPasswordPage() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("auth/pro/password/forgot", { body: { email } });
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <PortalAuthShell>
      <form className="stack" onSubmit={submit} style={{ gap: 18, flex: 1 }}>
        <div className="stack" style={{ gap: 6 }}>
          <h2 className="title">{t("forgotTitle")}</h2>
          <p className="ink2" style={{ margin: 0 }}>{t("forgotIntro")}</p>
        </div>
        {sent ? (
          <div className="banner green" role="status"><strong>{t("forgotSent")}</strong></div>
        ) : (
          <div className="field">
            <label htmlFor="email">{t("proEmail")}</label>
            <input id="email" className="input" type="email" autoComplete="username" inputMode="email" dir="ltr"
              value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
        )}
        {error && <p className="error" role="alert">{error}</p>}
        <div className="grow" />
        {!sent && (
          <button className="btn primary block tall" disabled={busy || !email}>
            {busy ? <span className="spinner sm" style={{ borderTopColor: "#fff" }} /> : t("sendLink")}
          </button>
        )}
        <Link href="/assureur/connexion" className="btn link" style={{ alignSelf: "center" }}>{t("backToLogin")}</Link>
      </form>
    </PortalAuthShell>
  );
}
