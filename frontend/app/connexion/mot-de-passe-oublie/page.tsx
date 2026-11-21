"use client";

import { ForgotPasswordForm } from "@/components/ProAuth";
import { PortalAuthShell } from "@/components/PortalAuthShell";

/** Mot de passe oublié, commun aux comptes professionnels (assureurs et entreprises). */
export default function ForgotPasswordPage() {
  return (
    <PortalAuthShell nameKey="proSpaceName">
      <ForgotPasswordForm />
    </PortalAuthShell>
  );
}
