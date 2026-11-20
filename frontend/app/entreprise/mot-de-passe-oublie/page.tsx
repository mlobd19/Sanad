"use client";

import { ForgotPasswordForm, COMPANY_SPACE } from "@/components/ProAuth";
import { PortalAuthShell } from "@/components/PortalAuthShell";

export default function CompanyForgotPasswordPage() {
  return (
    <PortalAuthShell nameKey="companySpace">
      <ForgotPasswordForm space={COMPANY_SPACE} />
    </PortalAuthShell>
  );
}
