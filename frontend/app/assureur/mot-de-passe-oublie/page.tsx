"use client";

import { ForgotPasswordForm, AGENT_SPACE } from "@/components/ProAuth";
import { PortalAuthShell } from "@/components/PortalAuthShell";

export default function ForgotPasswordPage() {
  return (
    <PortalAuthShell>
      <ForgotPasswordForm space={AGENT_SPACE} />
    </PortalAuthShell>
  );
}
