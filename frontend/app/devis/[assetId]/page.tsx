"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { Icon } from "@/components/Icon";
import { App, ErrorBox, Loading, Steps, TopBar, useUser } from "@/components/Shell";
import { api, ApiError, type Policy, type Quote } from "@/lib/api";
import { money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

function QuotesScreen() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const { assetId } = useParams<{ assetId: string }>();
  const search = useSearchParams();
  const renewalOf = search.get("renouvellement");
  const { user } = useUser();
  const [quotes, setQuotes] = useState<Quote[] | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const [startsOn, setStartsOn] = useState(search.get("debut") ?? new Date().toISOString().slice(0, 10));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setError("");
    api<Quote[]>(`assets/${assetId}/quotes`, { method: "POST" })
      .then((qs) => {
        setQuotes(qs);
        setPicked(qs[0]?.id ?? null);
      })
      .catch((e) => setError(e.message));
  }, [assetId]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  async function proceed() {
    if (!picked) return;
    setBusy(true);
    setError("");
    try {
      const policy = await api<Policy>("policies", {
        body: { quote_id: picked, starts_on: startsOn, ...(renewalOf ? { renewal_of: Number(renewalOf) } : {}) },
      });
      router.push(`/paiement/${policy.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("error"));
      setBusy(false);
    }
  }

  if (!quotes && !error) return <App><TopBar title={t("quotesTitle")} back="/vehicule" /><Loading /></App>;

  return (
    <App>
      <TopBar title={t("quotesTitle")} back="/vehicule" />
      <main className="content">
        <Steps n={3} />
        {error && <ErrorBox message={error} onRetry={quotes ? undefined : load} />}
        {quotes && quotes.length === 0 && <p className="muted">{t("noQuotes")}</p>}
        {quotes && quotes.length > 0 && (
          <>
            <h2 className="eyebrow">{t("quotesCount", { count: quotes.length })}</h2>
            <div className="stack" role="radiogroup">
              {quotes.map((q) => {
                const on = q.id === picked;
                return (
                  <button
                    key={q.id}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    className={`card${on ? " selected" : ""}`}
                    onClick={() => setPicked(q.id)}
                  >
                    <div className="between">
                      <div className="stack" style={{ gap: 2 }}>
                        <div className="row" style={{ gap: 8 }}>
                          <strong>{q.insurer}</strong>
                          {on && <span className="pill">{t("selected")}</span>}
                        </div>
                        <span className="small muted">{q.product}</span>
                      </div>
                      <span className="price">{money(q.premium, lang)}</span>
                    </div>
                    <div className="stack small" style={{ gap: 6, color: "var(--ink-2)" }}>
                      {q.coverages.map((c) => (
                        <span key={c} className="row" style={{ gap: 8 }}>
                          <span style={{ color: "var(--green)" }}><Icon name="check" size={16} strokeWidth={2.2} /></span>
                          {c}
                        </span>
                      ))}
                    </div>
                  </button>
                );
              })}
            </div>
            <div className="field">
              <label htmlFor="start">{t("startsOn")}</label>
              <input id="start" className="input" type="date" value={startsOn} onChange={(e) => setStartsOn(e.target.value)} />
            </div>
          </>
        )}
      </main>
      {quotes && quotes.length > 0 && (
        <div className="footer-cta">
          <button type="button" className="btn primary block" onClick={proceed} disabled={!picked || busy}>
            {t("continueToPay")}
          </button>
        </div>
      )}
    </App>
  );
}

export default function QuotesPage() {
  return (
    <Suspense fallback={<App><Loading /></App>}>
      <QuotesScreen />
    </Suspense>
  );
}
