"use client";

import { useRef, useState } from "react";

import { Icon } from "@/components/Icon";
import { Link } from "@/components/NavLink";
import { SecurePinPad } from "@/components/SecurePinPad";
import { api, ApiError } from "@/lib/api";
import { useI18n, type Key } from "@/lib/i18n";
import { tooSimplePin } from "@/lib/pin";
import { useSpace } from "@/lib/spaces";

type Step = "old" | "new" | "confirm" | "done";

const TITLES: Record<Exclude<Step, "done">, Key> = { old: "pinOldTitle", new: "pinNewTitle", confirm: "pinConfirmTitle" };

/** Profil › « Changer mon code » : code actuel, puis nouveau code deux fois. Ferme les autres appareils. */
export default function ChangePinPage() {
  const { t } = useI18n();
  useSpace("customer");
  const [step, setStep] = useState<Step>("old");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [round, setRound] = useState(0);
  // Codes saisis, gardés en mémoire le temps des trois étapes (jamais dans le navigateur).
  const codes = useRef({ old: "", new: "" });

  function go(next: Step, message = "") {
    if (next === "old") codes.current = { old: "", new: "" };
    setStep(next);
    setError(message);
    setRound((r) => r + 1);
  }

  async function onConfirm(pin: string) {
    if (pin !== codes.current.new) return go("new", t("pinMismatch"));
    setBusy(true);
    try {
      await api("auth/pin/change", { body: { old: codes.current.old, new: pin } });
      codes.current = { old: "", new: "" };
      setBusy(false);
      go("done");
    } catch (err) {
      setBusy(false);
      // 3 codes faux de suite : api() ferme la session et renvoie vers le code SMS.
      const code = err instanceof ApiError ? err.code : "";
      if (code === "pin_wrong") go("old", t("pinWrong", { n: Number((err as ApiError).data.attempts_left) || 1 }));
      else if (code === "pin_weak") go("new", t("pinTooSimple"));
      else go("old", err instanceof Error ? err.message : t("error"));
    }
  }

  function onComplete(pin: string) {
    if (step === "old") {
      codes.current.old = pin;
      go("new");
    } else if (step === "new") {
      if (tooSimplePin(pin)) return go("new", t("pinTooSimple"));
      codes.current.new = pin;
      go("confirm");
    } else onConfirm(pin);
  }

  if (step === "done") {
    return (
      <main className="content with-nav">
        <div className="banner green" role="status">
          <strong className="row" style={{ gap: 8 }}><Icon name="check" size={20} strokeWidth={3} />{t("pinChanged")}</strong>
        </div>
        <Link href="/profil" className="btn primary block">{t("pinBackToProfile")}</Link>
      </main>
    );
  }

  return (
    <main className="content with-nav pin-change">
      <SecurePinPad
        key={round}
        title={t(TITLES[step])}
        hint={step === "new" ? t("pinChooseHint") : step === "confirm" ? t("pinConfirmHint") : undefined}
        error={error}
        busy={busy}
        onComplete={onComplete}
      />
    </main>
  );
}
