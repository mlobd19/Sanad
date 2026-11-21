"use client";

import type { ReactNode } from "react";

import { Wordmark } from "@/components/Logo";
import { ThemeIconButton } from "@/components/ThemeChoice";
import { useI18n, type Key } from "@/lib/i18n";

/** Shell commun aux pages de connexion du portail (fond vert, carte blanche centrée). */
export function PortalAuthShell({ children, nameKey = "portalName", wide = false }: {
  children: ReactNode; nameKey?: Key; wide?: boolean;
}) {
  const { t, lang, setLang } = useI18n();
  return (
    <div className="portal-login">
      <div className={`box${wide ? " wide" : ""}`}>
        <div className="between">
          <Wordmark name={`${t("appName")} · ${t(nameKey)}`} size={20} onDark />
          <div className="head-actions">
            <button type="button" className="btn-on-dark" onClick={() => setLang(lang === "fr" ? "ar" : "fr")}>
              {lang === "fr" ? "العربية" : "Français"}
            </button>
            <ThemeIconButton />
          </div>
        </div>
        <main className="sheet" style={{ color: "var(--ink)" }}>{children}</main>
      </div>
    </div>
  );
}
