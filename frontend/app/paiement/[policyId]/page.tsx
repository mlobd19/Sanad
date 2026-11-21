"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { DURATION_LABEL } from "@/components/DurationPicker";
import { Icon } from "@/components/Icon";
import { App, ErrorBox, Loading, Stepper, TopBar } from "@/components/Shell";
import { api, ApiError, type PaymentStart, type Policy, type Provider } from "@/lib/api";
import { date, formatPlate, money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useSpace } from "@/lib/spaces";

export default function PaymentPage() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const { policyId } = useParams<{ policyId: string }>();
  const { user } = useSpace("customer");
  const [kycNeeded, setKycNeeded] = useState(false);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [provider, setProvider] = useState("");
  const [payer, setPayer] = useState("");
  const [payment, setPayment] = useState<PaymentStart | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!user) return;
    setPayer(user.phone);
    setKycNeeded(user.kyc_status !== "verified");
    Promise.all([api<Policy>(`policies/${policyId}`), api<Provider[]>("payments/providers")])
      .then(([p, list]) => {
        setPolicy(p);
        setProviders(list);
        setProvider(list[0]?.code ?? "");
      })
      .catch((e) => setError(e.message));
  }, [user, policyId]);

  const stopPolling = () => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
  };

  const poll = useCallback(async () => {
    const p = await api<Policy>(`policies/${policyId}`);
    setPolicy(p);
    if (p.status === "active") router.replace(`/contrats/${p.id}`);
    if (p.status !== "draft") stopPolling();
  }, [policyId, router]);

  useEffect(() => stopPolling, []);

  async function pay() {
    setBusy(true);
    setError("");
    try {
      const started = await api<PaymentStart>(`policies/${policyId}/pay`, { body: { provider, payer_phone: payer } });
      setPayment(started);
      stopPolling();
      timer.current = setInterval(() => poll().catch(() => undefined), 3000);
    } catch (err) {
      if (err instanceof ApiError && err.code === "kyc_required") setKycNeeded(true);
      else setError(err instanceof ApiError ? err.message : t("error"));
    } finally {
      setBusy(false);
    }
  }

  async function simulate() {
    if (!payment) return;
    setBusy(true);
    try {
      await api(`payments/${payment.payment_id}/simulate-confirm`, { method: "POST" });
      await poll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("error"));
    } finally {
      setBusy(false);
    }
  }

  function changeMethod() {
    stopPolling();
    setPayment(null);
  }

  const header = (
    <TopBar title={t("payTitle")} back="/">
      <Stepper current={2} />
    </TopBar>
  );

  if (!policy && !error) return <App>{header}<Loading /></App>;

  const providerLabel = providers.find((p) => p.code === provider)?.label ?? "";
  const waitingInsurer = policy?.status === "paid";

  return (
    <App>
      {header}
      <main className="content">
        {error && <ErrorBox message={error} />}
        {policy && (
          <section className="amount-card" aria-label={t("summary")}>
            <span className="sub">{policy.insurer} · {policy.product} · <bdi dir="ltr">{formatPlate(policy.plate)}</bdi></span>
            <span className="big">{money(policy.premium, lang)}</span>
            <span className="sub">{date(policy.starts_on, lang)} → {date(policy.ends_on, lang)} · {t(DURATION_LABEL[policy.duration_months])}</span>
          </section>
        )}

        {waitingInsurer ? (
          <div className="banner green" role="status" style={{ flexDirection: "column", alignItems: "stretch", gap: 12 }}>
            <strong style={{ fontSize: 16 }}>{t("waitingInsurer")}</strong>
            <Link className="btn outline block" href={`/contrats/${policyId}`}>{t("seeDetails")}</Link>
          </div>
        ) : payment ? (
          <section className="wait-card" role="status">
            <div className="row" style={{ gap: 14 }}>
              <span className="avatar" style={{ width: 52, height: 52, borderRadius: 26, background: "var(--sand-tint)", color: "var(--sand-text)" }}>
                <Icon name="phone" size={26} strokeWidth={2} />
              </span>
              <div className="stack" style={{ gap: 2 }}>
                <strong style={{ fontSize: 17 }}>{t("confirmOnPhone")}</strong>
                <span className="ink2" style={{ fontSize: 14 }}>{providerLabel} · <bdi>{payer}</bdi></span>
              </div>
            </div>
            <ol className="steps-num">
              <li><span>1</span>{t("payStep1", { provider: providerLabel })}</li>
              <li><span>2</span>{t("payStep2", { amount: money(payment.amount, lang) })}</li>
              <li><span>3</span>{t("payStep3")}</li>
            </ol>
            <div className="row" style={{ gap: 10, paddingTop: 12, borderTop: "1px solid var(--line)" }}>
              <span className="spinner sm" aria-hidden="true" />
              <span className="ink2" style={{ fontSize: 14 }}>
                {t("pendingRef")} <strong style={{ color: "var(--ink)" }}><bdi>{payment.reference}</bdi></strong>
              </span>
            </div>
            {provider === "simulated" && (
              <button type="button" className="btn outline block" onClick={simulate} disabled={busy}>{t("simulate")}</button>
            )}
          </section>
        ) : (
          policy?.status === "draft" && (
            <>
              {kycNeeded && (
                <div className={`banner ${user?.kyc_status === "rejected" ? "red" : "sand"}`} role="alert"
                  style={{ flexDirection: "column", alignItems: "stretch", gap: 12 }}>
                  <span>{t(user?.kyc_status === "rejected" ? "kycRejectedPay" : user?.kyc_status === "pending" ? "kycPendingPay" : "kycBeforePay")}</span>
                  {user?.kyc_status !== "rejected" && (
                    <Link className="btn primary block" href={`/profil?retour=/paiement/${policyId}`}>
                      <Icon name="shield" size={20} strokeWidth={2} />
                      {t("idCheck")}
                    </Link>
                  )}
                </div>
              )}
              <section className="stack">
                <h2 className="eyebrow">{t("method")}</h2>
                <div className="stack" role="radiogroup" aria-label={t("method")}>
                  {providers.map((p) => (
                    <button
                      key={p.code}
                      type="button"
                      role="radio"
                      aria-checked={provider === p.code}
                      className="radio"
                      onClick={() => setProvider(p.code)}
                    >
                      <span className="row" style={{ gap: 12 }}>
                        <span className="avatar" aria-hidden="true">{p.label.charAt(0)}</span>
                        {p.label}
                      </span>
                      <span className="dot" />
                    </button>
                  ))}
                </div>
              </section>
              <div className="field">
                <label htmlFor="payer">{t("payerPhone")}</label>
                <input id="payer" className="input" type="tel" value={payer} onChange={(e) => setPayer(e.target.value)} dir="ltr" />
                <span className="small ink2">{t("payHint")}</span>
              </div>
            </>
          )
        )}
      </main>
      {policy?.status === "draft" && (
        <div className="footer-cta">
          {payment ? (
            <>
              <button type="button" className="btn outline block" onClick={() => poll().catch(() => undefined)} disabled={busy}>
                {t("iPaid")}
              </button>
              <button type="button" className="btn link" onClick={changeMethod}>{t("changeMethod")}</button>
            </>
          ) : (
            <button type="button" className="btn primary block tall" onClick={pay} disabled={busy || !provider || kycNeeded}>
              {t("pay", { amount: money(policy.premium, lang) })}
            </button>
          )}
        </div>
      )}
    </App>
  );
}
