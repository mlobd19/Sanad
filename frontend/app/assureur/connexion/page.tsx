"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { OtpCodeForm, type OtpResult } from "@/components/OtpLogin";
import { PortalAuthShell } from "@/components/PortalAuthShell";
import { api, ApiError, setToken } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type Challenge = { challenge: string; phone: string };

export default function InsurerLoginPage() {
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
    if (res.user.role !== "insurer_agent") throw new Error(t("portalNotAgent"));
    setToken(res.token);
    if (res.user.language !== lang) await api("me", { method: "PATCH", body: { language: lang } });
    router.replace("/assureur");
  }

  async function resend() {
    // Un nouvel envoi repasse par email + mot de passe (gardés en mémoire le temps de la connexion).
    setPending(await api<Challenge>("auth/pro/login", { body: { email, password } }));
  }

  return (
    <PortalAuthShell>
      {pending ? (
        <OtpCodeForm
          sentTo={pending.phone}
          onSubmit={verify}
          onResend={resend}
          onBack={() => { setPending(null); setPassword(""); }}
          backLabel={t("changeAccount")}
        />
      ) : (
        <form className="stack" onSubmit={start} style={{ gap: 18, flex: 1 }}>
          <div className="stack" style={{ gap: 6 }}>
            <h2 className="title">{t("portalLoginTitle")}</h2>
            <p className="ink2" style={{ margin: 0 }}>{t("portalLoginIntro")}</p>
          </div>
          <div className="field">
            <label htmlFor="email">{t("proEmail")}</label>
            <input
              id="email"
              className="input"
              type="email"
              autoComplete="username"
              inputMode="email"
              dir="ltr"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <div className="between">
              <label htmlFor="password">{t("proPassword")}</label>
              <button type="button" className="btn link" style={{ minHeight: 32, fontSize: 14 }}
                onClick={() => setShowPassword((v) => !v)} aria-controls="password" aria-pressed={showPassword}>
                {t(showPassword ? "hidePassword" : "showPassword")}
              </button>
            </div>
            <input
              id="password"
              className="input"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              dir="ltr"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          {error && <p className="error" role="alert">{error}</p>}
          <Link href="/assureur/mot-de-passe-oublie" className="small" style={{ fontWeight: 700, alignSelf: "flex-start" }}>
            {t("forgotPassword")}
          </Link>
          <div className="grow" />
          <button className="btn primary block tall" disabled={busy || !email || !password}>
            {busy ? <span className="spinner sm" style={{ borderTopColor: "#fff" }} /> : t("continue")}
          </button>
        </form>
      )}
    </PortalAuthShell>
  );
}
