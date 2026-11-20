"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { PortalAuthShell } from "@/components/PortalAuthShell";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** Lien reçu par email (invitation ou mot de passe oublié) : /assureur/mot-de-passe?uid=…&token=… */
export default function SetPasswordPage() {
  return (
    <PortalAuthShell>
      <Suspense fallback={<span className="spinner" />}>
        <SetPasswordForm />
      </Suspense>
    </PortalAuthShell>
  );
}

function SetPasswordForm() {
  const { t } = useI18n();
  const params = useSearchParams();
  const uid = params.get("uid") ?? "";
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setError(t("passwordsDiffer"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api("auth/pro/password/reset", { body: { uid, token, password } });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("error"));
    } finally {
      setBusy(false);
    }
  }

  if (!uid || !token) {
    return (
      <div className="stack" style={{ gap: 16 }}>
        <h2 className="title">{t("resetTitle")}</h2>
        <p className="error" role="alert">{t("linkInvalid")}</p>
        <Link href="/assureur/mot-de-passe-oublie" className="btn primary block">{t("sendLink")}</Link>
      </div>
    );
  }

  if (done) {
    return (
      <div className="stack" style={{ gap: 16 }}>
        <h2 className="title">{t("resetTitle")}</h2>
        <div className="banner green" role="status"><strong>{t("passwordSaved")}</strong></div>
        <Link href="/assureur/connexion" className="btn primary block tall">{t("verify")}</Link>
      </div>
    );
  }

  return (
    <form className="stack" onSubmit={submit} style={{ gap: 18, flex: 1 }}>
      <div className="stack" style={{ gap: 6 }}>
        <h2 className="title">{t("resetTitle")}</h2>
        <p className="ink2" style={{ margin: 0 }}>{t("resetIntro")}</p>
      </div>
      <div className="field">
        <div className="between">
          <label htmlFor="new-password">{t("newPassword")}</label>
          <button type="button" className="btn link" style={{ minHeight: 32, fontSize: 14 }}
            onClick={() => setShow((v) => !v)} aria-controls="new-password confirm-password" aria-pressed={show}>
            {t(show ? "hidePassword" : "showPassword")}
          </button>
        </div>
        <input id="new-password" className="input" type={show ? "text" : "password"} autoComplete="new-password"
          dir="ltr" minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} required />
      </div>
      <div className="field">
        <label htmlFor="confirm-password">{t("confirmPassword")}</label>
        <input id="confirm-password" className="input" type={show ? "text" : "password"} autoComplete="new-password"
          dir="ltr" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="grow" />
      <button className="btn primary block tall" disabled={busy || password.length < 10 || !confirm}>
        {busy ? <span className="spinner sm" style={{ borderTopColor: "#fff" }} /> : t("savePassword")}
      </button>
    </form>
  );
}
