"use client";

import { SetPasswordForm } from "@/components/ProAuth";
import { PortalAuthShell } from "@/components/PortalAuthShell";

export default function SetPasswordPage() {
  return (
    <PortalAuthShell>
      <SetPasswordForm />
    </PortalAuthShell>
  );
}
