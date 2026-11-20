"use client";

import { ProLoginForm, AGENT_SPACE } from "@/components/ProAuth";
import { PortalAuthShell } from "@/components/PortalAuthShell";

export default function InsurerLoginPage() {
  return (
    <PortalAuthShell>
      <ProLoginForm space={AGENT_SPACE} titleKey="portalLoginTitle" introKey="portalLoginIntro" />
    </PortalAuthShell>
  );
}
