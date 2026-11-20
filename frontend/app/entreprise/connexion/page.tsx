"use client";

import Link from "next/link";

import { COMPANY_SPACE, ProLoginForm } from "@/components/ProAuth";
import { PortalAuthShell } from "@/components/PortalAuthShell";
import { useI18n } from "@/lib/i18n";

export default function CompanyLoginPage() {
  const { t } = useI18n();
  return (
    <PortalAuthShell nameKey="companySpace">
      <ProLoginForm
        space={COMPANY_SPACE}
        titleKey="companyLoginTitle"
        introKey="companyLoginIntro"
        footer={
          <p className="small ink2" style={{ margin: 0, textAlign: "center" }}>
            {t("companyNoAccount")} <Link href="/entreprise/inscription" style={{ fontWeight: 700 }}>{t("companySignupLink")}</Link>
          </p>
        }
      />
    </PortalAuthShell>
  );
}
