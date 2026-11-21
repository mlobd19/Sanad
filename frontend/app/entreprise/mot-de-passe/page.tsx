"use client";

import { SetPasswordForm } from "@/components/ProAuth";
import { PortalAuthShell } from "@/components/PortalAuthShell";

export default function CompanySetPasswordPage() {
  return (
    <PortalAuthShell nameKey="companySpace">
      <SetPasswordForm />
    </PortalAuthShell>
  );
}
