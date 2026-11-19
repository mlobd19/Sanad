"use client";

import { useRouter } from "next/navigation";

import { Wordmark } from "@/components/Logo";
import { OtpLogin, type OtpResult } from "@/components/OtpLogin";
import { api, setToken } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function LoginPage() {
  const { t, lang, setLang } = useI18n();
  const router = useRouter();

  async function onVerified({ token, user }: OtpResult) {
    setToken(token);
    if (user.language !== lang) await api("me", { method: "PATCH", body: { language: lang } });
    router.replace("/");
  }

  return (
    <div className="app" style={{ background: "var(--green-deep)" }}>
      <div style={{ padding: "28px 24px 32px", display: "flex", flexDirection: "column", gap: 28, color: "#fff" }}>
        <div className="between">
          <Wordmark name={t("appName")} size={22} onDark />
          <button type="button" className="btn-on-dark" onClick={() => setLang(lang === "fr" ? "ar" : "fr")}>
            {lang === "fr" ? "العربية" : "Français"}
          </button>
        </div>
        <h1 className="title" style={{ fontSize: 34, lineHeight: 1.12, color: "#fff" }}>{t("tagline")}</h1>
      </div>

      <main className="sheet">
        <OtpLogin title={t("loginTitle")} intro={t("loginIntro")} onVerified={onVerified} />
      </main>
    </div>
  );
}
