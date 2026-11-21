"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ClaimForm } from "@/components/ClaimForm";
import { App, ErrorBox, Loading, TopBar, useUser } from "@/components/Shell";
import { api, type Claim, type Policy } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function DeclareClaimPage() {
  const { t } = useI18n();
  const { policyId } = useParams<{ policyId: string }>();
  const { user } = useUser();
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [loadError, setLoadError] = useState("");
  const [sent, setSent] = useState<Claim | null>(null);

  useEffect(() => {
    if (user) api<Policy>(`policies/${policyId}`).then(setPolicy).catch((e) => setLoadError(e.message));
  }, [user, policyId]);

  const header = <TopBar title={t("declareClaim")} back={`/contrats/${policyId}`} />;
  if (!policy && !loadError) return <App>{header}<Loading /></App>;
  if (loadError || !policy) return <App>{header}<main className="content"><ErrorBox message={loadError} /></main></App>;

  if (sent) {
    return (
      <App>
        {header}
        <main className="content">
          <div className="banner green" role="status" style={{ flexDirection: "column", alignItems: "stretch", gap: 12 }}>
            <strong>{t("claimSent", { number: sent.number, insurer: policy.insurer })}</strong>
            <Link className="btn primary block" href={`/contrats/${policyId}`}>{t("seeDetails")}</Link>
          </div>
        </main>
      </App>
    );
  }

  if (policy.status !== "active" && policy.status !== "expired") {
    return <App>{header}<main className="content"><p className="banner sand">{t("claimErr_policy_inactive")}</p></main></App>;
  }

  return (
    <App>
      {header}
      <main className="content">
        <ClaimForm policy={policy} endpoint={`policies/${policyId}/claims`} onSent={setSent} />
      </main>
    </App>
  );
}
