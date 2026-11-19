"use client";

import { useEffect, useState } from "react";

import { api, apiBlobUrl, type Policy } from "@/lib/api";
import { daysUntil } from "@/lib/format";

/** Charge une police et l'image QR de son attestation (si elle existe). */
export function usePolicyQr(policyId: string, enabled: boolean) {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!enabled) return;
    let url: string | null = null;
    api<Policy>(`policies/${policyId}`)
      .then(async (p) => {
        setPolicy(p);
        if (p.attestation) {
          url = await apiBlobUrl(`attestations/${p.attestation.id}/qr.png`);
          setQr(url);
        }
      })
      .catch((e) => setError(e.message));
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [policyId, enabled]);

  const valid =
    !!policy?.attestation &&
    policy.status === "active" &&
    policy.attestation.status === "valid" &&
    daysUntil(policy.starts_on) <= 0 &&
    daysUntil(policy.ends_on) >= 0;

  return { policy, qr, error, valid };
}
