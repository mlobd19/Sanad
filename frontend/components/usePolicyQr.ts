"use client";

import { useEffect, useState } from "react";

import { api, apiBlobUrl, type Policy } from "@/lib/api";
import { cache } from "@/lib/cache";
import { daysUntil } from "@/lib/format";
import { cachedPolicy } from "@/lib/useLoad";

/** Charge une police et l'image QR de son attestation (si elle existe). La dernière version connue
 *  (contrat ou liste des contrats, lib/cache.ts) s'affiche tout de suite, pendant l'actualisation. */
export function usePolicyQr(policyId: string, enabled: boolean) {
  const [policy, setPolicy] = useState<Policy | null>(() => cachedPolicy(policyId));
  const [qr, setQr] = useState<string | null>(() => {
    const known = cachedPolicy(policyId)?.attestation;
    return known ? cache.get<string>(`qr/${known.id}`) ?? null : null;
  });
  const [error, setError] = useState("");

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    api<Policy>(`policies/${policyId}`)
      .then(async (p) => {
        cache.set(`policies/${policyId}`, p);
        if (!alive) return;
        setPolicy(p);
        if (p.attestation) {
          const key = `qr/${p.attestation.id}`;
          // Image gardée avec le reste du cache (libérée à la déconnexion) : pas de nouveau téléchargement.
          let url = cache.get<string>(key);
          if (!url) {
            url = await apiBlobUrl(`attestations/${p.attestation.id}/qr.png`);
            cache.set(key, url);
          }
          if (alive) setQr(url);
        }
      })
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
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
