"use client";

import { useEffect, useState } from "react";

import { useI18n } from "@/lib/i18n";

/** Bandeau « Démonstration » en haut de chaque écran quand l'instance tourne en DEMO_MODE (lu sur /api/meta). */
export function DemoBanner() {
  const { t } = useI18n();
  const [demo, setDemo] = useState(false);

  useEffect(() => {
    fetch("/api/meta")
      .then((r) => (r.ok ? r.json() : null))
      .then((meta) => setDemo(Boolean(meta?.demo_mode)))
      .catch(() => setDemo(false));
  }, []);

  if (!demo) return null;
  return (
    <div className="demo-banner" role="note">
      <strong>{t("demoBannerTitle")}</strong> · {t("demoBannerText")}
    </div>
  );
}
