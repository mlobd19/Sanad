"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

import { ClaimsSection } from "@/components/ClaimsSection";
import { useHideTopBar } from "@/components/ClientChrome";
import { Icon } from "@/components/Icon";
import { InsurerLogo } from "@/components/InsurerLogo";
import { SanadMark } from "@/components/Logo";
import { Link } from "@/components/NavLink";
import { ErrorBox, ErrorLine, StatusPill } from "@/components/Shell";
import { ContractSkeleton } from "@/components/Skeletons";
import { AssistanceLink, LimitsList, TripSummary, VerificationPill } from "@/components/Travel";
import { usePolicyQr } from "@/components/usePolicyQr";
import { ApiError, downloadFile, type Policy } from "@/lib/api";
import { date, formatPlate } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useSpace } from "@/lib/spaces";

export default function ContractPage() {
  const { t, lang } = useI18n();
  const { policyId } = useParams<{ policyId: string }>();
  const { user } = useSpace("customer");
  const { policy, qr, error } = usePolicyQr(policyId, !!user);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfError, setPdfError] = useState("");

  async function downloadPdf(attestationId: number, number: string) {
    setPdfBusy(true);
    setPdfError("");
    try {
      await downloadFile(`attestations/${attestationId}/pdf`, `attestation-${number}.pdf`);
    } catch (err) {
      setPdfError(err instanceof ApiError ? err.message : t("error"));
    } finally {
      setPdfBusy(false);
    }
  }

  async function share() {
    if (!policy?.attestation) return;
    const url = policy.attestation.verify_url;
    if (navigator.share) {
      await navigator.share({ title: t("attestationTitle"), text: policy.attestation.number, url }).catch(() => undefined);
    } else {
      await navigator.clipboard?.writeText(url);
    }
  }

  const att = policy?.attestation;
  const insured = Boolean(policy?.status === "active" && att);
  // Contrat assuré : l'en-tête vert de l'écran remplace la barre du haut du layout.
  useHideTopBar(insured);

  return (
    <>
      {insured && (
        <header className="success-head">
          <div className="row" style={{ gap: 6 }}>
            <Link href="/" className="iconbtn" aria-label={t("back")}><Icon name="back" size={24} strokeWidth={2.2} /></Link>
            <h1>{t("contractTitle")}</h1>
          </div>
          <div className="row" style={{ padding: "0 6px" }}>
            <span className="avatar" style={{ width: 40, height: 40, background: "var(--on-green)", color: "var(--green)" }}>
              <Icon name="check" size={22} strokeWidth={3} />
            </span>
            <div className="stack" style={{ gap: 2 }}>
              <strong style={{ fontFamily: "var(--display)", fontSize: 20 }}>{t("youreInsured")}</strong>
              <span style={{ fontSize: 14, color: "var(--green-soft)" }}>{t("alsoSms")}</span>
            </div>
          </div>
        </header>
      )}

      <main className="content">
        {error && <ErrorBox message={error} />}
        {!policy && !error && <ContractSkeleton />}
        {policy?.status === "paid" && <div className="banner sand" role="status"><strong>{t("waitingInsurer")}</strong></div>}
        {policy?.status === "refused" && (
          <div className="banner red">{t("refusedText", { reason: policy.refusal_reason })}</div>
        )}

        {policy?.trip ? (
          <TravelContract policy={policy} trip={policy.trip} pdfBusy={pdfBusy} onPdf={downloadPdf} pdfError={pdfError} />
        ) : policy && att ? (
          <>
            <section className="card attestation" aria-label={t("attestationTitle")}>
              <header>
                <div>
                  <small>{t("attestationShort")}</small>
                  <strong>N° <bdi>{att.number}</bdi></strong>
                </div>
                <SanadMark size={30} color="var(--on-ink)" />
              </header>
              <div className="body">
                {qr ? <img className="qr" src={qr} alt="QR code" /> : <div className="qr" aria-hidden="true" />}
                <div className="kv">
                  <div><span>{t("plate")}</span><strong><bdi dir="ltr">{formatPlate(policy.plate)}</bdi></strong></div>
                  <div><span>{t("validUntil")}</span><strong>{date(policy.ends_on, lang)}</strong></div>
                  <div>
                    <span>{t("insurer")}</span>
                    <div className="row" style={{ gap: 8, marginTop: 4 }}>
                      {policy.insurer_logo && <InsurerLogo name={policy.insurer} logo={policy.insurer_logo} size={32} />}
                      <strong style={{ fontSize: 14 }}>{policy.insurer} · {policy.product}</strong>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            <Link className="btn primary block tall" href={`/contrats/${policy.id}/controle`}>
              <Icon name="expand" size={22} strokeWidth={2.2} />
              {t("showForControl")}
            </Link>
            <ErrorLine message={pdfError} />
            <div className="grid2">
              <button
                type="button"
                className="btn outline"
                onClick={() => downloadPdf(att.id, att.number)}
                disabled={pdfBusy}
                aria-label={t("downloadPdf")}
              >
                {pdfBusy ? <span className="spinner sm" /> : <Icon name="download" size={18} strokeWidth={2} />}
                {t("download")}
              </button>
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
                <span className="plate"><bdi dir="ltr">{formatPlate(policy.plate)}</bdi></span>
                <StatusPill status={policy.status} />
              </div>
              <span className="ink2">{policy.insurer} · {policy.product}</span>
              <span className="small ink2">{date(policy.starts_on, lang)} → {date(policy.ends_on, lang)}</span>
            </section>
          )
        )}
        {policy && (policy.status === "active" || policy.status === "expired") && <ClaimsSection policy={policy} />}
      </main>
    </>
  );
}

/** Contrat voyage : voyage, assistance 24 h/24, attestation de chaque voyageur, garanties et plafonds. */
function TravelContract({ policy, trip, pdfBusy, pdfError, onPdf }: {
  policy: Policy;
  trip: NonNullable<Policy["trip"]>;
  pdfBusy: boolean;
  pdfError: string;
  onPdf: (attestationId: number, number: string) => void;
}) {
  const { t, lang } = useI18n();
  return (
    <>
      <section className="card">
        <div className="between" style={{ alignItems: "flex-start" }}>
          <div className="row" style={{ gap: 10 }}>
            <span className="iconbox" aria-hidden="true"><Icon name="plane" /></span>
            <div className="stack" style={{ gap: 2 }}>
              <strong>{policy.insurer} · {policy.product}</strong>
              <span className="small ink2"><TripSummary trip={trip} travelers={trip.travelers.length} /></span>
            </div>
          </div>
          {policy.status !== "active" && <StatusPill status={policy.status} />}
        </div>
      </section>
      {policy.status === "active" && <AssistanceLink phone={policy.assistance_phone} insurer={policy.insurer} />}

      <h2 className="eyebrow" style={{ margin: 0 }}>{t("travelAttestations")}</h2>
      <ul className="stack" style={{ gap: 10, listStyle: "none", padding: 0, margin: 0 }}>
        {trip.travelers.map((x) => (
          <li key={x.id} className="card" style={{ gap: 8 }}>
            <div className="between" style={{ alignItems: "flex-start" }}>
              <div className="stack" style={{ gap: 2, minWidth: 0 }}>
                <strong>{lang === "ar" && x.full_name_ar ? x.full_name_ar : x.full_name}</strong>
                <span className="small ink2">
                  <bdi dir="ltr">{t("passportShort", { passport: x.passport_number })}</bdi> · {t("bornOn", { date: date(x.birth_date, lang) })}
                </span>
              </div>
              <VerificationPill verification={x.verification} />
            </div>
            {x.attestation && policy.status === "active" && (
              <div className="between" style={{ gap: 8 }}>
                <bdi className="small" dir="ltr">N° <strong>{x.attestation.number}</strong></bdi>
                <div className="row" style={{ gap: 6 }}>
                  <a className="btn link" href={x.attestation.verify_url} target="_blank" rel="noreferrer">{t("verifyLink")}</a>
                  <button type="button" className="btn outline" style={{ minHeight: 44, padding: "0 14px" }}
                    onClick={() => onPdf(x.attestation!.id, x.attestation!.number)} disabled={pdfBusy}
                    aria-label={`${t("downloadPdf")} · ${t("attestationOf", { name: x.full_name })}`}>
                    <Icon name="download" size={18} strokeWidth={2} />
                    {t("pdf")}
                  </button>
                </div>
              </div>
            )}
          </li>
        ))}
      </ul>
      <ErrorLine message={pdfError} />

      <section className="card" aria-label={t("limitsTitle")}>
        <strong>{t("limitsTitle")}</strong>
        <LimitsList limits={policy.limits} />
        <span className="small muted">{date(policy.starts_on, lang)} → {date(policy.ends_on, lang)}</span>
      </section>
    </>
  );
}
