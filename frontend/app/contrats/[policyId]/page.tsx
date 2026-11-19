"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Icon } from "@/components/Icon";
import { KhaimaMark } from "@/components/Logo";
import { App, ErrorBox, Loading, StatusPill, TopBar, useUser } from "@/components/Shell";
import { api, apiBlobUrl, type Policy } from "@/lib/api";
import { date } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

export default function ContractPage() {
  const { t, lang } = useI18n();
  const { policyId } = useParams<{ policyId: string }>();
  const { user } = useUser();
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!user) return;
    api<Policy>(`policies/${policyId}`)
      .then((p) => {
        setPolicy(p);
        if (p.attestation) return apiBlobUrl(`attestations/${p.attestation.id}/qr.png`).then(setQr);
      })
      .catch((e) => setError(e.message));
  }, [user, policyId]);

  useEffect(() => () => { if (qr) URL.revokeObjectURL(qr); }, [qr]);

  async function share() {
    if (!policy?.attestation) return;
    const url = policy.attestation.verify_url;
    if (navigator.share) {
      await navigator.share({ title: t("attestationTitle"), text: policy.attestation.number, url }).catch(() => undefined);
    } else {
      await navigator.clipboard?.writeText(url);
    }
  }

  if (!policy && !error) return <App><TopBar title={t("contractTitle")} back="/contrats" /><Loading /></App>;

  const att = policy?.attestation;

  return (
    <App>
      <TopBar title={t("contractTitle")} back="/contrats" />
      <main className="content">
        {error && <ErrorBox message={error} />}
        {policy && (
          <>
            {policy.status === "active" && (
              <div className="banner green">
                <Icon name="check" strokeWidth={2.4} />
                <strong className="grow">{t("paymentConfirmed")}</strong>
              </div>
            )}
            {policy.status === "paid" && <div className="banner sand" role="status">{t("waitingInsurer")}</div>}
            {policy.status === "refused" && (
              <div className="banner red">{t("refusedText", { reason: policy.refusal_reason })}</div>
            )}

            {att ? (
              <section className="card attestation" aria-label={t("attestationTitle")}>
                <header>
                  <div>
                    <small>{t("attestationTitle")}</small>
                    <strong>N° <bdi>{att.number}</bdi></strong>
                  </div>
                  <KhaimaMark size={30} color="#8fd3b8" />
                </header>
                <div className="body">
                  <div className="kv">
                    <div><span>{t("insured")}</span><strong>{user?.full_name || user?.phone}</strong></div>
                    <div><span>{t("plate")}</span><strong><bdi>{policy.plate}</bdi></strong></div>
                    <div><span>{t("insurer")}</span><strong>{policy.insurer}</strong></div>
                    <div><span>{t("cover")}</span><strong>{policy.product}</strong></div>
                    <div><span>{t("validFrom")}</span><strong>{date(policy.starts_on, lang)}</strong></div>
                    <div><span>{t("validTo")}</span><strong>{date(policy.ends_on, lang)}</strong></div>
                  </div>
                  <div className="qrrow">
                    {qr ? <img src={qr} alt="QR code" /> : <div className="qrph" aria-hidden="true" />}
                    <div className="stack" style={{ gap: 6 }}>
                      <strong>{t("signed")}</strong>
                      <span className="small" style={{ color: "var(--ink-2)", lineHeight: 1.45 }}>{t("signedText")}</span>
                    </div>
                  </div>
                </div>
              </section>
            ) : (
              <section className="card">
                <div className="between">
                  <strong>{policy.insurer} · {policy.product}</strong>
                  <StatusPill status={policy.status} />
                </div>
                <span className="small muted"><bdi>{policy.plate}</bdi> · {date(policy.starts_on, lang)} → {date(policy.ends_on, lang)}</span>
              </section>
            )}

            {att && (
              <>
                <div className="grid3" style={{ gridTemplateColumns: "1fr 1fr" }}>
                  {qr && (
                    <a className="btn outline" href={qr} download={`${att.number}.png`}>
                      <Icon name="download" size={18} />
                      {t("downloadQr")}
                    </a>
                  )}
                  <button type="button" className="btn outline" onClick={share}>
                    <Icon name="share" size={18} />
                    {t("share")}
                  </button>
                </div>
                <a href={att.verify_url} target="_blank" rel="noreferrer" className="small" style={{ textAlign: "center", fontWeight: 600 }}>
                  {t("openCheck")}
                </a>
              </>
            )}
          </>
        )}
      </main>
    </App>
  );
}
