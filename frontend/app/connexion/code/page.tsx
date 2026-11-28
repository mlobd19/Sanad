"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { LanguageButton } from "@/components/LanguageButton";
import { StackedLogo } from "@/components/Logo";
import { SecurePinPad } from "@/components/SecurePinPad";
import { ThemeIconButton } from "@/components/ThemeChoice";
import { api, ApiError, getToken, setToken, type User } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { tooSimplePin, type PinStatus } from "@/lib/pin";
import { logout, safeReturn } from "@/lib/spaces";

type Mode = "loading" | "choose" | "confirm" | "enter";

/**
 * Code PIN des particuliers (backend : accounts/pin.py).
 * - Juste après le code SMS : « Choisissez votre code » puis « Confirmez votre code ».
 * - Ouvertures suivantes sur cet appareil : « Entrez votre code », sans SMS ; « Code oublié ? » → SMS.
 */
export default function PinPage() {
  return (
    <Suspense fallback={<div className="app" style={{ background: "var(--green-deep)" }} />}>
      <Pin />
    </Suspense>
  );
}

function Pin() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const [mode, setMode] = useState<Mode>("loading");
  const [status, setStatus] = useState<PinStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [round, setRound] = useState(0); // nouvelle `key` du pavé : saisie vidée, chiffres de nouveau mélangés
  const first = useRef(""); // code choisi, en attente de confirmation (mémoire seulement)
  const back = safeReturn(params.get("retour"));

  useEffect(() => {
    if (!getToken()) {
      router.replace("/connexion");
      return;
    }
    api<PinStatus>("auth/pin")
      .then((s) => {
        if (s.state === "open") router.replace(back);
        else {
          setStatus(s);
          setMode(s.state === "setup" ? "choose" : "enter");
        }
      })
      .catch((err) => {
        // 401 : jeton expiré ou révoqué (api() l'a oublié) ; 403 : compte pro, renvoyé vers son espace.
        router.replace(err instanceof ApiError && err.status === 403 ? "/" : "/connexion");
      });
  }, [router, back]);

  function step(next: Mode, message = "") {
    first.current = next === "confirm" ? first.current : "";
    setMode(next);
    setError(message);
    setRound((r) => r + 1);
  }

  async function finish(user: User) {
    if (user.language !== lang) await api("me", { method: "PATCH", body: { language: lang } }).catch(() => undefined);
    router.replace(back);
  }

  /** Retour au code SMS, avec la raison affichée sur la page de connexion. */
  function backToSms(reason: string) {
    setToken(null);
    router.replace(`/connexion?raison=${reason}`);
  }

  async function send(path: "setup" | "unlock", pin: string) {
    setBusy(true);
    try {
      const r = await api<{ user: User }>(`auth/pin/${path}`, { body: { pin } });
      await finish(r.user);
    } catch (err) {
      setBusy(false);
      const code = err instanceof ApiError ? err.code : "";
      const left = err instanceof ApiError ? Number(err.data.attempts_left) || 1 : 1;
      if (code === "pin_blocked" || code === "pin_setup_expired") backToSms(code);
      else if (code === "pin_weak") step("choose", t("pinTooSimple"));
      else if (code === "pin_wrong") step("enter", t("pinWrong", { n: left }));
      else step(path === "setup" ? "choose" : "enter", err instanceof Error ? err.message : t("error"));
    }
  }

  function onChoose(pin: string) {
    if (tooSimplePin(pin)) return step("choose", t("pinTooSimple"));
    first.current = pin;
    step("confirm");
  }

  function onConfirm(pin: string) {
    if (pin !== first.current) return step("choose", t("pinMismatch"));
    send("setup", pin);
  }

  // Nom du client (identité vérifiée), sinon la fin de son numéro, masqué.
  const name = status ? (lang === "ar" && status.full_name_ar) || status.full_name : "";
  const greeting = name ? t("helloName", { name }) : <bdi dir="ltr">•• •• •• {status?.phone_end}</bdi>;

  return (
    <div className="app" style={{ background: "var(--green-deep)" }}>
      <div className="pin-head">
        <div className="head-actions" style={{ justifyContent: "flex-end" }}>
          <LanguageButton />
          <ThemeIconButton />
        </div>
        <StackedLogo size={56} onDark />
      </div>

      <main className="sheet pin-sheet">
        {mode === "loading" ? (
          <div className="center" style={{ minHeight: 240 }}><span className="spinner" aria-label={t("loading")} /></div>
        ) : mode === "enter" ? (
          <SecurePinPad
            key={round}
            title={t("pinEnterTitle")}
            hint={greeting}
            error={error}
            busy={busy}
            onComplete={(pin) => send("unlock", pin)}
            footer={
              <button type="button" className="btn link pin-forgot" onClick={() => logout(router)} disabled={busy}>
                {t("pinForgot")}
              </button>
            }
          />
        ) : (
          <SecurePinPad
            key={round}
            title={t(mode === "choose" ? "pinChooseTitle" : "pinConfirmTitle")}
            hint={t(mode === "choose" ? "pinChooseHint" : "pinConfirmHint")}
            error={error}
            busy={busy}
            onComplete={mode === "choose" ? onChoose : onConfirm}
            footer={mode === "confirm" ? (
              <button type="button" className="btn link pin-forgot" onClick={() => step("choose")} disabled={busy}>
                {t("pinRestart")}
              </button>
            ) : <span className="pin-forgot" aria-hidden="true" />}
          />
        )}
      </main>
    </div>
  );
}
