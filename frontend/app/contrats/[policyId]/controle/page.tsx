"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect } from "react";

import { Icon } from "@/components/Icon";
import { Loading, ErrorBox, useUser } from "@/components/Shell";
import { usePolicyQr } from "@/components/usePolicyQr";
import { date } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

/** Plein écran à montrer lors d'un contrôle routier : grand QR, plaque, validité. */
export default function ControlPage() {
  const { t, lang } = useI18n();
  const { policyId } = useParams<{ policyId: string }>();
  const { user } = useUser();
  const { policy, qr, error, valid } = usePolicyQr(policyId, !!user);

  // Garde l'écran allumé pendant le contrôle, quand le navigateur le permet.
  useEffect(() => {
    let lock: { release: () => Promise<void> } | null = null;
    const nav = navigator as Navigator & { wakeLock?: { request: (t: "screen") => Promise<{ release: () => Promise<void> }> } };
    nav.wakeLock?.request("screen").then((l) => (lock = l)).catch(() => undefined);
    return () => {
      lock?.release().catch(() => undefined);
    };
  }, []);

  if (error) return <main className="control"><ErrorBox message={error} /></main>;
  if (!policy) return <main className="control"><Loading /></main>;
  const att = policy.attestation;

  return (
    <main className="control">
      <div className="between" style={{ alignSelf: "stretch" }}>
        <span className={`pill${valid ? "" : " bad"}`}>{valid ? `✓ ${t("valid")}` : t("notValid")}</span>
        <Link href={`/contrats/${policy.id}`} className="iconbtn ring" aria-label={t("close")}>
          <Icon name="close" size={22} strokeWidth={2.6} />
        </Link>
      </div>

      <div className="stack" style={{ alignItems: "center", gap: 4, textAlign: "center" }}>
        <span style={{ fontSize: 14, fontWeight: 700, color: "var(--ink-2)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
          {t("attestationShort")}
        </span>
        <span className="plate"><bdi>{policy.plate}</bdi></span>
      </div>

      {qr ? <img className="qr" src={qr} alt="QR code" /> : <div className="qr" aria-hidden="true" />}

      <div className="facts">
        <div><span>{t("validUntil")}</span><strong>{date(policy.ends_on, lang)}</strong></div>
        <div><span>{t("insurer")}</span><strong>{policy.insurer}</strong></div>
      </div>
      {att && <strong style={{ fontSize: 15 }}>N° <bdi>{att.number}</bdi></strong>}
      <div className="grow" />
      <p className="ink2" style={{ fontSize: 14, textAlign: "center", lineHeight: 1.5, margin: 0 }}>
        {t("controlHint")}
        <br />
        {t("worksOffline")}
      </p>
    </main>
  );
}
