"use client";

import { useEffect, useRef, useState, type ClipboardEvent, type FormEvent, type KeyboardEvent } from "react";

import { api, ApiError, type User } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const RESEND_DELAY = 30;

export type OtpResult = { token: string; user: User };

function formatPhone(digits: string) {
  return digits.replace(/\D/g, "").slice(0, 8).replace(/(\d{2})(?=\d)/g, "$1 ");
}

function message(err: unknown, fallback: string) {
  return err instanceof Error && err.message ? err.message : fallback;
}

// --- Étape « code à 6 chiffres » (particuliers et comptes professionnels) ---------------

type CodeProps = {
  /** Numéro affiché après « Envoyé par SMS au » (complet ou masqué). */
  sentTo: string;
  /** Vérifie le code ; une erreur levée s'affiche et vide les cases. */
  onSubmit: (code: string) => Promise<void>;
  /** Renvoie un code ; une erreur levée s'affiche. */
  onResend: () => Promise<void>;
  onBack: () => void;
  backLabel: string;
};

export function OtpCodeForm({ sentTo, onSubmit, onResend, onBack, backLabel }: CodeProps) {
  const { t } = useI18n();
  const [digits, setDigits] = useState<string[]>(Array(6).fill(""));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [wait, setWait] = useState(RESEND_DELAY);
  const boxes = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    boxes.current[0]?.focus();
  }, []);

  useEffect(() => {
    if (wait <= 0) return;
    const id = setTimeout(() => setWait((w) => w - 1), 1000);
    return () => clearTimeout(id);
  }, [wait]);

  async function submit(code: string) {
    setBusy(true);
    setError("");
    try {
      await onSubmit(code);
    } catch (err) {
      setError(message(err, t("error")));
      setDigits(Array(6).fill(""));
      setBusy(false);
      setTimeout(() => boxes.current[0]?.focus(), 0);
    }
  }

  async function resend() {
    setBusy(true);
    setError("");
    try {
      await onResend();
      setDigits(Array(6).fill(""));
      setWait(RESEND_DELAY);
      boxes.current[0]?.focus();
    } catch (err) {
      setError(message(err, t("error")));
    } finally {
      setBusy(false);
    }
  }

  function fill(values: string[]) {
    setDigits(values);
    const code = values.join("");
    if (code.length === 6 && !busy) submit(code);
  }

  function onDigit(i: number, value: string) {
    const clean = value.replace(/\D/g, "");
    if (!clean) {
      const next = [...digits];
      next[i] = "";
      setDigits(next);
      return;
    }
    const next = [...digits];
    clean.split("").slice(0, 6 - i).forEach((d, k) => (next[i + k] = d));
    boxes.current[Math.min(i + clean.length, 5)]?.focus();
    fill(next);
  }

  function onKey(i: number, e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace" && !digits[i] && i > 0) boxes.current[i - 1]?.focus();
  }

  function onPaste(e: ClipboardEvent<HTMLInputElement>) {
    const clean = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (clean.length) {
      e.preventDefault();
      fill(clean.padEnd(6, " ").split("").map((d) => d.trim()));
      boxes.current[Math.min(clean.length, 5)]?.focus();
    }
  }

  return (
    <form className="stack" onSubmit={(e) => { e.preventDefault(); submit(digits.join("")); }} style={{ gap: 22, flex: 1 }}>
      <div className="stack" style={{ gap: 6 }}>
        <h2 className="title">{t("codeTitle")}</h2>
        <p className="ink2" style={{ margin: 0 }}>
          {t("codeSentShort")} <strong style={{ color: "var(--ink)" }}><bdi dir="ltr">{sentTo}</bdi></strong>
        </p>
      </div>
      <fieldset className="field" style={{ border: "none", padding: 0, margin: 0 }}>
        <legend style={{ marginBottom: 8 }}>{t("codeDigits")}</legend>
        <div className="otp" dir="ltr">
          {digits.map((d, i) => (
            <input
              key={i}
              ref={(el) => { boxes.current[i] = el; }}
              className={d ? "filled" : ""}
              inputMode="numeric"
              autoComplete={i === 0 ? "one-time-code" : "off"}
              aria-label={t("codeDigit", { n: i + 1 })}
              value={d}
              maxLength={i === 0 ? 6 : 1}
              onChange={(e) => onDigit(i, e.target.value)}
              onKeyDown={(e) => onKey(i, e)}
              onPaste={onPaste}
              disabled={busy}
            />
          ))}
        </div>
        <span className="small muted" style={{ marginTop: 6 }}>{t("codeAuto")}</span>
      </fieldset>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="between">
        <button type="button" className="btn link" onClick={onBack}>{backLabel}</button>
        {wait > 0 ? (
          <span className="ink2 small">
            {t("resendIn")} <strong style={{ color: "var(--ink)" }}>0:{String(wait).padStart(2, "0")}</strong>
          </span>
        ) : (
          <button type="button" className="btn link" onClick={resend} disabled={busy}>{t("resend")}</button>
        )}
      </div>
      <div className="grow" />
      <button className="btn primary block tall" disabled={busy || digits.join("").length !== 6}>
        {busy ? <span className="spinner sm" /> : t("verify")}
      </button>
    </form>
  );
}

// --- Connexion des particuliers : numéro puis code -----------------------------------------

type Props = {
  title: string;
  intro: string;
  /**
   * Appelé après un code valide, avant toute mise en session. Si la fonction lève
   * une erreur, son message s'affiche et le formulaire revient à l'étape « numéro ».
   */
  onVerified: (result: OtpResult) => Promise<void>;
};

export function OtpLogin({ title, intro, onVerified }: Props) {
  const { t } = useI18n();
  const [phone, setPhone] = useState("");
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

  async function verify(code: string) {
    const result = await api<OtpResult>("auth/otp/verify", { body: { phone, code } }); // erreur → affichée sous le code
    try {
      await onVerified(result);
    } catch (err) {
      // Le code est consommé : on repart du numéro.
      setError(message(err, t("error")));
      setStep("phone");
    }
  }

  if (step === "code") {
    return (
      <OtpCodeForm
        sentTo={`+222 ${formatPhone(phone)}`}
        onSubmit={verify}
        onResend={() => api("auth/otp/request", { body: { phone } }).then(() => undefined)}
        onBack={() => { setStep("phone"); setError(""); }}
        backLabel={t("changeNumber")}
      />
    );
  }

  return (
    <form className="stack" onSubmit={sendCode} style={{ gap: 20, flex: 1 }}>
      <div className="stack" style={{ gap: 6 }}>
        <h2 className="title">{title}</h2>
        <p className="ink2" style={{ margin: 0 }}>{intro}</p>
      </div>
      <div className="field">
        <label htmlFor="phone">{t("phoneLabel")}</label>
        <div className="row" style={{ gap: 8 }} dir="ltr">
          <span className="input" style={{ width: "auto", display: "flex", alignItems: "center", background: "var(--bg)", fontWeight: 700 }}>
            +222
          </span>
          <input
            id="phone"
            className="input"
            type="tel"
            inputMode="numeric"
            autoComplete="tel-national"
            placeholder={t("phonePlaceholder")}
            value={formatPhone(phone)}
            onChange={(e) => setPhone(e.target.value.replace(/\D/g, "").slice(0, 8))}
            style={{ fontWeight: 600, letterSpacing: "0.04em" }}
            required
          />
        </div>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="grow" />
      <button className="btn primary block tall" disabled={busy || phone.length < 8}>{t("sendCode")}</button>
    </form>
  );
}
