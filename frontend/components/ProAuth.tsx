"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent, type ReactNode } from "react";

import { OtpCodeForm, type OtpResult } from "@/components/OtpLogin";
import { api, ApiError, setToken } from "@/lib/api";
import { useI18n, type Key } from "@/lib/i18n";
import { enterSpace, loginUrl } from "@/lib/spaces";

/** Pages communes aux comptes professionnels (assureurs et entreprises). */
export const FORGOT_PASSWORD_URL = "/connexion/mot-de-passe-oublie";
const PRO_LOGIN_URL = loginUrl("company_member"); // /connexion?espace=pro

type Challenge = { challenge: string; phone: string };

function PasswordField({ id, label, value, onChange, autoComplete, show, onToggle, minLength }: {
  id: string; label: string; value: string; onChange: (v: string) => void; autoComplete: string;
  show: boolean; onToggle?: () => void; minLength?: number;
}) {
  const { t } = useI18n();
  return (
    <div className="field">
      <div className="between">
        <label htmlFor={id}>{label}</label>
        {onToggle && (
          <button type="button" className="btn link" style={{ minHeight: 32, fontSize: 14 }}
            onClick={onToggle} aria-controls={id} aria-pressed={show}>
            {t(show ? "hidePassword" : "showPassword")}
          </button>
        )}
      </div>
      <input id={id} className="input" type={show ? "text" : "password"} autoComplete={autoComplete} dir="ltr"
        minLength={minLength} value={value} onChange={(e) => onChange(e.target.value)} required />
    </div>
  );
}

/** Email + mot de passe, puis code SMS. Le compte arrive ensuite dans son espace (assureur ou entreprise). */
export function ProLoginForm({ titleKey, introKey, footer }: { titleKey: Key; introKey: Key; footer?: ReactNode }) {
  const { t, lang } = useI18n();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [pending, setPending] = useState<Challenge | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function start(e?: FormEvent) {
    e?.preventDefault();
    setBusy(true);
    setError("");
    try {
      setPending(await api<Challenge>("auth/pro/login", { body: { email, password } }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("error"));
    } finally {
      setBusy(false);
    }
  }

  async function verify(code: string) {
    const res = await api<OtpResult>("auth/pro/verify", { body: { challenge: pending?.challenge, code } });
    setToken(res.token);
    if (res.user.language !== lang) await api("me", { method: "PATCH", body: { language: lang } });
    enterSpace(router, res.user);
  }

  async function resend() {
    // Un nouvel envoi repasse par email + mot de passe (gardés en mémoire le temps de la connexion).
    setPending(await api<Challenge>("auth/pro/login", { body: { email, password } }));
  }

  if (pending) {
    return (
      <OtpCodeForm
        sentTo={pending.phone}
        onSubmit={verify}
        onResend={resend}
        onBack={() => { setPending(null); setPassword(""); }}
        backLabel={t("changeAccount")}
      />
    );
  }

  return (
    <form className="stack" onSubmit={start} style={{ gap: 18, flex: 1 }}>
      <div className="stack" style={{ gap: 6 }}>
        <h2 className="title">{t(titleKey)}</h2>
        <p className="ink2" style={{ margin: 0 }}>{t(introKey)}</p>
      </div>
      <div className="field">
        <label htmlFor="email">{t("proEmail")}</label>
        <input id="email" className="input" type="email" autoComplete="username" inputMode="email" dir="ltr"
          value={email} onChange={(e) => setEmail(e.target.value)} required />
      </div>
      <PasswordField id="password" label={t("proPassword")} value={password} onChange={setPassword}
        autoComplete="current-password" show={showPassword} onToggle={() => setShowPassword((v) => !v)} />
      {error && <p className="error" role="alert">{error}</p>}
      <Link href={FORGOT_PASSWORD_URL} className="small" style={{ fontWeight: 700, alignSelf: "flex-start" }}>
        {t("forgotPassword")}
      </Link>
      <div className="grow" />
      <button className="btn primary block tall" disabled={busy || !email || !password}>
        {busy ? <span className="spinner sm" style={{ borderTopColor: "#fff" }} /> : t("continue")}
      </button>
      {footer}
    </form>
  );
}

export function ForgotPasswordForm() {
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
      <Link href={PRO_LOGIN_URL} className="btn link" style={{ alignSelf: "center" }}>{t("backToLogin")}</Link>
    </form>
  );
}

/** Lien reçu par email (invitation ou mot de passe oublié) : …/mot-de-passe?uid=…&token=… */
export function SetPasswordForm() {
  return (
    <Suspense fallback={<span className="spinner" />}>
      <SetPasswordInner />
    </Suspense>
  );
}

function SetPasswordInner() {
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
        <Link href={FORGOT_PASSWORD_URL} className="btn primary block">{t("sendLink")}</Link>
      </div>
    );
  }

  if (done) {
    return (
      <div className="stack" style={{ gap: 16 }}>
        <h2 className="title">{t("resetTitle")}</h2>
        <div className="banner green" role="status"><strong>{t("passwordSaved")}</strong></div>
        <Link href={PRO_LOGIN_URL} className="btn primary block tall">{t("verify")}</Link>
      </div>
    );
  }

  return (
    <form className="stack" onSubmit={submit} style={{ gap: 18, flex: 1 }}>
      <div className="stack" style={{ gap: 6 }}>
        <h2 className="title">{t("resetTitle")}</h2>
        <p className="ink2" style={{ margin: 0 }}>{t("resetIntro")}</p>
      </div>
      <PasswordField id="new-password" label={t("newPassword")} value={password} onChange={setPassword}
        autoComplete="new-password" show={show} onToggle={() => setShow((v) => !v)} minLength={10} />
      <PasswordField id="confirm-password" label={t("confirmPassword")} value={confirm} onChange={setConfirm}
        autoComplete="new-password" show={show} />
      {error && <p className="error" role="alert">{error}</p>}
      <div className="grow" />
      <button className="btn primary block tall" disabled={busy || password.length < 10 || !confirm}>
        {busy ? <span className="spinner sm" style={{ borderTopColor: "#fff" }} /> : t("savePassword")}
      </button>
    </form>
  );
}

export { PasswordField };
