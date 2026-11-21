"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { OtpCodeForm, type OtpResult } from "@/components/OtpLogin";
import { PasswordField } from "@/components/ProAuth";
import { PortalAuthShell } from "@/components/PortalAuthShell";
import { api, ApiError, setToken } from "@/lib/api";
import { useI18n, type Key } from "@/lib/i18n";

type Form = {
  legal_name: string; nif: string; rc_number: string; address: string;
  full_name: string; email: string; phone: string; password: string;
};

const EMPTY: Form = { legal_name: "", nif: "", rc_number: "", address: "", full_name: "", email: "", phone: "", password: "" };

export default function CompanySignupPage() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const [form, setForm] = useState<Form>(EMPTY);
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [pending, setPending] = useState<{ challenge: string; phone: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const set = (key: keyof Form) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  async function send() {
    return api<{ challenge: string; phone: string }>("company/signup", {
      body: { ...form, phone: `+222${form.phone.replace(/\D/g, "")}`, language: lang },
    });
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (form.password !== confirm) {
      setError(t("passwordsDiffer"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      setPending(await send());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("error"));
    } finally {
      setBusy(false);
    }
  }

  async function verify(code: string) {
    const res = await api<OtpResult>("company/signup/verify", { body: { challenge: pending?.challenge, code } });
    setToken(res.token);
    router.replace("/entreprise?onglet=entreprise");
  }

  if (pending) {
    return (
      <PortalAuthShell nameKey="companySpace">
        <OtpCodeForm
          sentTo={pending.phone}
          onSubmit={verify}
          onResend={async () => { setPending(await send()); }}
          onBack={() => setPending(null)}
          backLabel={t("back")}
        />
      </PortalAuthShell>
    );
  }

  const text = (key: keyof Form, label: Key, extra: Record<string, string> = {}) => (
    <div className="field">
      <label htmlFor={`signup-${key}`}>{t(label)}</label>
      <input id={`signup-${key}`} className="input" value={form[key]} onChange={(e) => set(key)(e.target.value)}
        required={key !== "address"} {...extra} />
    </div>
  );

  return (
    <PortalAuthShell nameKey="companySpace" wide>
      <form className="stack" onSubmit={submit} style={{ gap: 18 }}>
        <div className="stack" style={{ gap: 6 }}>
          <h2 className="title">{t("signupTitle")}</h2>
          <p className="ink2" style={{ margin: 0 }}>{t("signupIntro")}</p>
        </div>

        <fieldset className="form-section">
          <legend>{t("signupCompany")}</legend>
          <div className="form-grid">
            {text("legal_name", "legalName", { autoComplete: "organization" })}
            {text("nif", "nifLabel", { dir: "ltr", inputMode: "text" })}
            {text("rc_number", "rcLabel", { dir: "ltr" })}
            {text("address", "addressLabel", { autoComplete: "street-address" })}
          </div>
        </fieldset>

        <fieldset className="form-section">
          <legend>{t("signupAdmin")}</legend>
          <div className="form-grid">
            {text("full_name", "fullName", { autoComplete: "name" })}
            {text("email", "proEmail", { type: "email", autoComplete: "username", dir: "ltr", inputMode: "email" })}
            <div className="field">
              <label htmlFor="signup-phone">{t("phoneLabel")}</label>
              <div className="row" style={{ gap: 8 }} dir="ltr">
                <span className="input" style={{ width: "auto", display: "flex", alignItems: "center", background: "var(--bg)", fontWeight: 700 }}>+222</span>
                <input id="signup-phone" className="input" type="tel" inputMode="numeric" autoComplete="tel-national"
                  placeholder={t("phonePlaceholder")} value={form.phone}
                  onChange={(e) => set("phone")(e.target.value.replace(/\D/g, "").slice(0, 8))} required />
              </div>
              <span className="small muted">{t("signupPhoneHint")}</span>
            </div>
            <div />
            <PasswordField id="signup-password" label={t("proPassword")} value={form.password} onChange={set("password")}
              autoComplete="new-password" show={show} onToggle={() => setShow((v) => !v)} minLength={10} />
            <PasswordField id="signup-confirm" label={t("confirmPassword")} value={confirm} onChange={setConfirm}
              autoComplete="new-password" show={show} />
          </div>
          <span className="small muted">{t("resetIntro")}</span>
        </fieldset>

        <p className="note" style={{ margin: 0 }}>{t("signupDocsNote")}</p>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn primary block tall" disabled={busy || form.phone.length < 8 || form.password.length < 10}>
          {busy ? <span className="spinner sm" style={{ borderTopColor: "#fff" }} /> : t("signupSubmit")}
        </button>
        <p className="small ink2" style={{ margin: 0, textAlign: "center" }}>
          {t("companyHasAccount")} <Link href="/connexion?espace=pro" style={{ fontWeight: 700 }}>{t("verify")}</Link>
        </p>
      </form>
    </PortalAuthShell>
  );
}
