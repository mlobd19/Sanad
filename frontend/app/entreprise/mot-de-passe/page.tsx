"use client";

import { SetPasswordForm, COMPANY_SPACE } from "@/components/ProAuth";
import { PortalAuthShell } from "@/components/PortalAuthShell";

export default function CompanySetPasswordPage() {
  return (
    <PortalAuthShell nameKey="companySpace">
      <SetPasswordForm space={COMPANY_SPACE} />
    </PortalAuthShell>
  );
}
