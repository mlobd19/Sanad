"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { App, ErrorBox, Loading, Steps, TopBar, useUser } from "@/components/Shell";
import { api, ApiError, type PaymentStart, type Policy, type Provider } from "@/lib/api";
import { money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

export default function PaymentPage() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const { policyId } = useParams<{ policyId: string }>();
  const { user } = useUser();
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
    Promise.all([api<Policy>(`policies/${policyId}`), api<Provider[]>("payments/providers")])
      .then(([p, list]) => {
        setPolicy(p);
        setProviders(list);
        setProvider(list[0]?.code ?? "");
      })
      .catch((e) => setError(e.message));
  }, [user, policyId]);

  const poll = useCallback(async () => {
    const p = await api<Policy>(`policies/${policyId}`);
    setPolicy(p);
    if (p.status === "active") router.replace(`/contrats/${p.id}`);
    if (p.status !== "draft" && timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  }, [policyId, router]);

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  async function pay() {
    setBusy(true);
    setError("");
    try {
      const started = await api<PaymentStart>(`policies/${policyId}/pay`, { body: { provider, payer_phone: payer } });
      setPayment(started);
      if (timer.current) clearInterval(timer.current);
      timer.current = setInterval(() => poll().catch(() => undefined), 3000);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("error"));
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

  if (!policy && !error) return <App><TopBar title={t("payTitle")} back="/" /><Loading /></App>;

  const waitingInsurer = policy?.status === "paid";

  return (
    <App>
      <TopBar title={t("payTitle")} back="/" />
      <main className="content">
        <Steps n={4} />
        {error && <ErrorBox message={error} />}
        {policy && (
          <section className="card">
            <h2 className="eyebrow">{t("summary")}</h2>
            <div className="between"><span className="muted">{t("offer")}</span><strong>{policy.insurer} · {policy.product}</strong></div>
            <div className="between"><span className="muted">{t("vehicle")}</span><strong><bdi>{policy.plate}</bdi></strong></div>
            <div className="between"><span className="muted">{t("period")}</span><strong>{t("twelveMonths")}</strong></div>
            <hr style={{ border: 0, borderTop: "1px solid var(--line)", margin: 0, width: "100%" }} />
            <div className="between">
              <strong>{t("total")}</strong>
              <span className="price" style={{ fontSize: 22 }}>{money(policy.premium, lang)}</span>
            </div>
          </section>
        )}

        {waitingInsurer ? (
          <div className="banner green" role="status">
            <span className="grow">{t("waitingInsurer")}</span>
            <Link className="btn outline" href={`/contrats/${policyId}`}>{t("seeDetails")}</Link>
          </div>
        ) : payment ? (
          <div className="stack">
            <div className="banner sand" role="status">
              <div className="spinner" style={{ width: 22, height: 22 }} />
              <span className="grow">{t("waitingConfirm")}</span>
            </div>
            <span className="small muted">Réf. <bdi>{payment.reference}</bdi></span>
            {provider === "simulated" && (
              <button type="button" className="btn outline block" onClick={simulate} disabled={busy}>
                {t("simulate")}
              </button>
            )}
          </div>
        ) : (
          policy?.status === "draft" && (
            <>
              <section className="stack">
                <h2 className="eyebrow">{t("method")}</h2>
                <div className="stack" role="radiogroup">
                  {providers.map((p) => (
                    <button
                      key={p.code}
                      type="button"
                      role="radio"
                      aria-checked={provider === p.code}
                      className="radio"
                      onClick={() => setProvider(p.code)}
                    >
                      <strong>{p.label}</strong>
                      <span className="dot" />
                    </button>
                  ))}
                </div>
              </section>
              <div className="field">
                <label htmlFor="payer">{t("payerPhone")}</label>
                <input id="payer" className="input" type="tel" value={payer} onChange={(e) => setPayer(e.target.value)} dir="ltr" />
                <span className="small muted">{t("payHint")}</span>
              </div>
            </>
          )
        )}
      </main>
      {policy?.status === "draft" && !payment && (
        <div className="footer-cta">
          <button type="button" className="btn primary block" onClick={pay} disabled={busy || !provider}>
            {t("pay", { amount: money(policy.premium, lang) })}
          </button>
        </div>
      )}
    </App>
  );
}
