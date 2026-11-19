"use client";

import { useRouter } from "next/navigation";

import { Wordmark } from "@/components/Logo";
import { OtpLogin, type OtpResult } from "@/components/OtpLogin";
import { api, setToken } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function InsurerLoginPage() {
  const { t, lang, setLang } = useI18n();
  const router = useRouter();

  async function onVerified({ token, user }: OtpResult) {
    // Un compte client ne doit pas ouvrir de session ici.
    if (user.role !== "insurer_agent") throw new Error(t("portalNotAgent"));
    setToken(token);
    if (user.language !== lang) await api("me", { method: "PATCH", body: { language: lang } });
    router.replace("/assureur");
  }

  return (
    <div className="portal-login">
      <div className="box">
        <div className="between">
          <Wordmark name={`${t("appName")} · ${t("portalName")}`} size={20} onDark />
          <button type="button" className="btn-on-dark" onClick={() => setLang(lang === "fr" ? "ar" : "fr")}>
            {lang === "fr" ? "العربية" : "Français"}
          </button>
        </div>
        <main className="sheet" style={{ color: "var(--ink)" }}>
          <OtpLogin title={t("portalLoginTitle")} intro={t("portalLoginIntro")} onVerified={onVerified} />
        </main>
      </div>
    </div>
  );
}
