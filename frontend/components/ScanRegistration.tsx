"use client";

import { useRef, useState, type ChangeEvent } from "react";

import { Icon } from "@/components/Icon";
import { ApiError, apiUpload, type RegistrationScan } from "@/lib/api";
import { useI18n, type Key } from "@/lib/i18n";

const ERRORS: Record<string, Key> = {
  not_card: "scanNotCard",
  unreadable: "scanUnreadable",
  too_large: "scanUnreadable",
  missing: "scanUnreadable",
  failed: "scanUnreadable",
  unavailable: "scanUnavailable",
};

/**
 * Bouton « Scanner la carte grise » : ouvre l'appareil photo (ou la galerie),
 * envoie la photo à l'API qui renvoie les champs lus, puis les passe au formulaire.
 * Le client vérifie toujours les champs avant de valider.
 */
export function ScanRegistration({ onRead }: { onRead: (fields: RegistrationScan) => void }) {
  const { t } = useI18n();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ tone: "green" | "sand" | "red"; key: Key } | null>(null);

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // permet de reprendre la même photo
    if (!file) return;
    setBusy(true);
    setStatus(null);
    const form = new FormData();
    form.append("image", file);
    try {
      const fields = await apiUpload<RegistrationScan>("assets/scan", form);
      onRead(fields);
      const complete = fields.reference && fields.make && fields.fiscal_power;
      setStatus(complete ? { tone: "green", key: "scanDone" } : { tone: "sand", key: "scanPartial" });
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "";
      setStatus({ tone: "red", key: ERRORS[code] ?? (err instanceof ApiError && err.status === 429 ? "scanUnavailable" : "error") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack" style={{ gap: 8 }}>
      <input ref={input} type="file" accept="image/*" capture="environment" hidden onChange={onFile} />
      <button type="button" className="btn outline block" disabled={busy} onClick={() => input.current?.click()}
        aria-describedby="scan-hint">
        {busy ? <span className="spinner sm" aria-hidden="true" /> : <Icon name="camera" size={22} strokeWidth={2} />}
        {busy ? t("scanReading") : t("scanCard")}
      </button>
      <span id="scan-hint" className="small muted">{t("scanHint")} {t("scanPrivacy")}</span>
      <div aria-live="polite">
        {status && <p className={`banner ${status.tone}`} role={status.tone === "red" ? "alert" : "status"} style={{ margin: 0 }}>{t(status.key)}</p>}
      </div>
    </div>
  );
}
