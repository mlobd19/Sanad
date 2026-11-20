"use client";

import { SetPasswordForm, AGENT_SPACE } from "@/components/ProAuth";
import { PortalAuthShell } from "@/components/PortalAuthShell";

export default function SetPasswordPage() {
  return (
    <PortalAuthShell>
      <SetPasswordForm space={AGENT_SPACE} />
    </PortalAuthShell>
  );
}
