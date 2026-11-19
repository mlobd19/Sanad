"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { Icon } from "@/components/Icon";
import { KhaimaMark } from "@/components/Logo";
import { App, ErrorBox, Loading, StatusPill, TopBar, useUser } from "@/components/Shell";
import { usePolicyQr } from "@/components/usePolicyQr";
import { date } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

export default function ContractPage() {
  const { t, lang } = useI18n();
  const { policyId } = useParams<{ policyId: string }>();
  const { user } = useUser();
  const { policy, qr, error } = usePolicyQr(policyId, !!user);

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
  const insured = policy?.status === "active" && att;

  return (
    <App>
      {insured ? (
        <header className="success-head">
          <div className="row" style={{ gap: 6 }}>
            <Link href="/" className="iconbtn" aria-label={t("back")}><Icon name="back" size={24} strokeWidth={2.2} /></Link>
            <h1>{t("contractTitle")}</h1>
          </div>
          <div className="row" style={{ padding: "0 6px" }}>
            <span className="avatar" style={{ width: 40, height: 40, background: "#fff", color: "var(--green)" }}>
              <Icon name="check" size={22} strokeWidth={3} />
            </span>
            <div className="stack" style={{ gap: 2 }}>
              <strong style={{ fontFamily: "var(--display)", fontSize: 20 }}>{t("youreInsured")}</strong>
              <span style={{ fontSize: 14, color: "var(--green-soft)" }}>{t("alsoWhatsapp")}</span>
            </div>
          </div>
        </header>
      ) : (
        <TopBar title={t("contractTitle")} back="/contrats" />
      )}

      <main className="content">
        {error && <ErrorBox message={error} />}
        {policy?.status === "paid" && <div className="banner sand" role="status"><strong>{t("waitingInsurer")}</strong></div>}
        {policy?.status === "refused" && (
          <div className="banner red">{t("refusedText", { reason: policy.refusal_reason })}</div>
        )}

        {policy && att ? (
          <>
            <section className="card attestation" aria-label={t("attestationTitle")}>
              <header>
                <div>
                  <small>{t("attestationShort")}</small>
                  <strong>N° <bdi>{att.number}</bdi></strong>
                </div>
                <KhaimaMark size={30} color="#fff" />
              </header>
              <div className="body">
                {qr ? <img className="qr" src={qr} alt="QR code" /> : <div className="qr" aria-hidden="true" />}
                <div className="kv">
                  <div><span>{t("plate")}</span><strong><bdi>{policy.plate}</bdi></strong></div>
                  <div><span>{t("validUntil")}</span><strong>{date(policy.ends_on, lang)}</strong></div>
                  <div><span>{t("insurer")}</span><strong style={{ fontSize: 14 }}>{policy.insurer} · {policy.product}</strong></div>
                </div>
              </div>
            </section>

            <Link className="btn primary block tall" href={`/contrats/${policy.id}/controle`}>
              <Icon name="expand" size={22} strokeWidth={2.2} />
              {t("showForControl")}
            </Link>
            <div className="grid2">
              {qr ? (
                <a className="btn outline" href={qr} download={`${att.number}.png`}>
                  <Icon name="download" size={18} strokeWidth={2} />
                  {t("downloadQr")}
                </a>
              ) : <span />}
              <button type="button" className="btn outline" onClick={share}>
                <Icon name="share" size={18} strokeWidth={2} />
                {t("share")}
              </button>
            </div>
            <p className="small ink2" style={{ textAlign: "center", margin: 0, lineHeight: 1.45 }}>{t("signedShort")}</p>
            <a href={att.verify_url} target="_blank" rel="noreferrer" className="small" style={{ textAlign: "center", fontWeight: 700 }}>
              {t("openCheck")}
            </a>
          </>
        ) : (
          policy && (
            <section className="card">
              <div className="between">
                <span className="plate"><bdi>{policy.plate}</bdi></span>
                <StatusPill status={policy.status} />
              </div>
              <span className="ink2">{policy.insurer} · {policy.product}</span>
              <span className="small ink2">{date(policy.starts_on, lang)} → {date(policy.ends_on, lang)}</span>
            </section>
          )
        )}
      </main>
    </App>
  );
}
