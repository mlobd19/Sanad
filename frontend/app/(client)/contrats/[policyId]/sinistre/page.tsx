"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

import { ClaimForm } from "@/components/ClaimForm";
import { Link } from "@/components/NavLink";
import { ErrorBox } from "@/components/Shell";
import { FormSkeleton } from "@/components/Skeletons";
import { type Claim, type Policy } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSpace } from "@/lib/spaces";
import { cachedPolicy, useLoad } from "@/lib/useLoad";

export default function DeclareClaimPage() {
  const { t } = useI18n();
  const { policyId } = useParams<{ policyId: string }>();
  const { user } = useSpace("customer");
  const loaded = useLoad<Policy>(`policies/${policyId}`, !!user);
  const policy = loaded.data ?? cachedPolicy(policyId);
  const loadError = loaded.error;
  const [sent, setSent] = useState<Claim | null>(null);

  if (!policy && !loadError) return <main className="content"><FormSkeleton fields={4} /></main>;
  if (!policy) return <main className="content"><ErrorBox message={loadError} /></main>;

  if (sent) {
    return (
      <main className="content">
        <div className="banner green" role="status" style={{ flexDirection: "column", alignItems: "stretch", gap: 12 }}>
          <strong>{t("claimSent", { number: sent.number, insurer: policy.insurer })}</strong>
          <Link className="btn primary block" href={`/contrats/${policyId}`}>{t("seeDetails")}</Link>
        </div>
      </main>
    );
  }

  if (policy.status !== "active" && policy.status !== "expired") {
    return <main className="content"><p className="banner sand">{t("claimErr_policy_inactive")}</p></main>;
  }

  return (
    <main className="content">
      <ClaimForm policy={policy} endpoint={`policies/${policyId}/claims`} onSent={setSent} />
    </main>
  );
}
