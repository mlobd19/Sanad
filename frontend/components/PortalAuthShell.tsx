"use client";

import type { ReactNode } from "react";

import { Wordmark } from "@/components/Logo";
import { useI18n } from "@/lib/i18n";

/** Shell commun aux pages de connexion du portail (fond vert, carte blanche centrée). */
export function PortalAuthShell({ children }: { children: ReactNode }) {
  const { t, lang, setLang } = useI18n();
  return (
    <div className="portal-login">
      <div className="box">
        <div className="between">
          <Wordmark name={`${t("appName")} · ${t("portalName")}`} size={20} onDark />
          <button type="button" className="btn-on-dark" onClick={() => setLang(lang === "fr" ? "ar" : "fr")}>
            {lang === "fr" ? "العربية" : "Français"}
          </button>
        </div>
        <main className="sheet" style={{ color: "var(--ink)" }}>{children}</main>
      </div>
    </div>
  );
}
