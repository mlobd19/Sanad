"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { KhaimaMark } from "@/components/Logo";
import { App } from "@/components/Shell";
import { api, ApiError, setToken, type User } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function LoginPage() {
  const { t, lang, setLang } = useI18n();
  const router = useRouter();
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function sendCode(e?: FormEvent) {
    e?.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("auth/otp/request", { body: { phone } });
      setStep("code");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("error"));
    } finally {
      setBusy(false);
    }
  }

  async function verify(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api<{ token: string; user: User }>("auth/otp/verify", { body: { phone, code } });
      setToken(res.token);
      if (res.user.language !== lang) await api("me", { method: "PATCH", body: { language: lang } });
      router.replace("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <App>
      <main className="content" style={{ justifyContent: "center", gap: 28 }}>
        <div className="between" style={{ alignItems: "center" }}>
          <span className="wordmark" style={{ fontSize: 22 }}>
            <KhaimaMark size={36} title={t("appName")} />
            {t("appName")}
          </span>
          <button type="button" className="btn outline" onClick={() => setLang(lang === "fr" ? "ar" : "fr")}>
            {lang === "fr" ? "العربية" : "Français"}
          </button>
        </div>

        <div className="stack">
          <h1 className="title" style={{ fontSize: 30 }}>{t("tagline")}</h1>
          <p className="muted" style={{ margin: 0 }}>{t("loginIntro")}</p>
        </div>

        {step === "phone" ? (
          <form className="stack" onSubmit={sendCode} style={{ gap: 14 }}>
            <div className="field">
              <label htmlFor="phone">{t("phoneLabel")}</label>
              <div className="row" style={{ gap: 8 }} dir="ltr">
                <span className="input" style={{ width: "auto", display: "flex", alignItems: "center", background: "var(--bg)" }}>
                  +222
                </span>
                <input
                  id="phone"
                  className="input"
                  type="tel"
                  inputMode="numeric"
                  autoComplete="tel-national"
                  placeholder={t("phonePlaceholder")}
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  required
                />
              </div>
            </div>
            {error && <p className="error" role="alert">{error}</p>}
            <button className="btn primary block" disabled={busy || phone.replace(/\D/g, "").length < 8}>
              {t("sendCode")}
            </button>
          </form>
        ) : (
          <form className="stack" onSubmit={verify} style={{ gap: 14 }}>
            <p className="small muted" style={{ margin: 0 }}>{t("codeSentTo", { phone: `+222 ${phone}` })}</p>
            <div className="field">
              <label htmlFor="code">{t("codeLabel")}</label>
              <input
                id="code"
                className="input code"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                dir="ltr"
                autoFocus
                required
              />
            </div>
            {error && <p className="error" role="alert">{error}</p>}
            <button className="btn primary block" disabled={busy || code.length !== 6}>{t("verify")}</button>
            <div className="between">
              <button type="button" className="btn ghost" onClick={() => { setStep("phone"); setCode(""); setError(""); }}>
                {t("changeNumber")}
              </button>
              <button type="button" className="btn ghost" onClick={() => sendCode()} disabled={busy}>
                {t("resend")}
              </button>
            </div>
          </form>
        )}
      </main>
    </App>
  );
}
