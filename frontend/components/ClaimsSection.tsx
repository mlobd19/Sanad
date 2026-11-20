"use client";

import Link from "next/link";

import { Icon } from "@/components/Icon";
import type { Claim, ClaimStatus, Policy } from "@/lib/api";
import { date, num } from "@/lib/format";
import { useI18n, type Key } from "@/lib/i18n";
import { useLoad } from "@/lib/useLoad";

const STATUS_PILL: Record<ClaimStatus, string> = { submitted: "pill warn", in_review: "pill warn", closed: "pill quiet" };

/** Sinistres d'un contrat en cours ou échu : suivi et accès à la déclaration. */
export function ClaimsSection({ policy }: { policy: Policy }) {
  const { t, lang } = useI18n();
  const { data: claims } = useLoad<Claim[]>(`policies/${policy.id}/claims`);

  return (
    <section className="card" aria-labelledby="claims-title">
      <h2 id="claims-title" className="eyebrow" style={{ margin: 0 }}>{t("claimsTitle")}</h2>
      {claims && claims.length === 0 && <p className="small ink2" style={{ margin: 0 }}>{t("noClaims")}</p>}
      {claims?.map((c) => (
        <article key={c.id} className="stack" style={{ gap: 4, paddingBlock: 8, borderTop: "1px solid var(--line)" }}>
          <div className="between">
            <strong><bdi dir="ltr">{c.number}</bdi></strong>
            <span className={STATUS_PILL[c.status]}>{t(`claimStatus_${c.status}` as Key)}</span>
          </div>
          <span className="small ink2">
            {t(`claimKind_${c.kind}` as Key)} · {date(c.occurred_on, lang)}
            {c.photos > 0 && ` · ${t("claimPhotoCount", { n: num(c.photos, lang) })}`}
          </span>
          {c.closing_note && (
            <p className="banner sand small" style={{ margin: 0, flexDirection: "column", alignItems: "flex-start", gap: 2 }}>
              <strong>{t("claimInsurerNote")}</strong>
              <span>{c.closing_note}</span>
            </p>
          )}
        </article>
      ))}
      <Link className="btn outline block" href={`/contrats/${policy.id}/sinistre`}>
        <Icon name="file" size={20} strokeWidth={2} />
        {t("declareClaim")}
      </Link>
    </section>
  );
}
