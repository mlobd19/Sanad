"use client";

import { useParams } from "next/navigation";
import { useEffect } from "react";

import { Icon } from "@/components/Icon";
import { InsurerLogo } from "@/components/InsurerLogo";
import { Link } from "@/components/NavLink";
import { ErrorBox } from "@/components/Shell";
import { ControlSkeleton } from "@/components/Skeletons";
import { usePolicyQr } from "@/components/usePolicyQr";
import { date, formatPlate } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useSpace } from "@/lib/spaces";

/** Plein écran à montrer lors d'un contrôle routier : grand QR, plaque, validité. */
export default function ControlPage() {
  const { t, lang } = useI18n();
  const { policyId } = useParams<{ policyId: string }>();
  const { user } = useSpace("customer");
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

  // Hors réseau pendant un contrôle : la dernière version connue reste affichée.
  if (!policy) return <main className="control">{error ? <ErrorBox message={error} /> : <ControlSkeleton />}</main>;
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
        <span className="plate"><bdi dir="ltr">{formatPlate(policy.plate)}</bdi></span>
      </div>

      {qr ? <img className="qr" src={qr} alt="QR code" /> : <div className="qr" aria-hidden="true" />}

      <div className="facts">
        <div><span>{t("validUntil")}</span><strong>{date(policy.ends_on, lang)}</strong></div>
        <div>
          <span>{t("insurer")}</span>
          {policy.insurer_logo && <InsurerLogo name={policy.insurer} logo={policy.insurer_logo} size={40} />}
          <strong>{policy.insurer}</strong>
        </div>
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
