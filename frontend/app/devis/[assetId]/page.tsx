"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { Icon } from "@/components/Icon";
import { App, ErrorBox, Loading, Stepper, TopBar, useUser } from "@/components/Shell";
import { api, ApiError, type Asset, type Policy, type Quote } from "@/lib/api";
import { date, money } from "@/lib/format";
import { useI18n, type Key } from "@/lib/i18n";

/** Lettre de l'avatar : initiale du dernier mot du nom, sans les mentions entre parenthèses. */
function initial(name: string) {
  const words = name.replace(/\(.*?\)/g, "").trim().split(/\s+/);
  return (words.at(-1) ?? name).charAt(0).toUpperCase();
}

const USAGE: Record<string, Key> = { personal: "usagePersonal", commercial: "usageCommercial", taxi: "usageTaxi" };

function QuotesScreen() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const { assetId } = useParams<{ assetId: string }>();
  const search = useSearchParams();
  const renewalOf = search.get("renouvellement");
  const { user } = useUser();
  const [asset, setAsset] = useState<Asset | null>(null);
  const [quotes, setQuotes] = useState<Quote[] | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const [startsOn, setStartsOn] = useState(search.get("debut") ?? new Date().toISOString().slice(0, 10));
  const [editDate, setEditDate] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const dateInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    setError("");
    api<Asset[]>("assets").then((list) => setAsset(list.find((a) => String(a.id) === assetId) ?? null)).catch(() => undefined);
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

  useEffect(() => {
    if (editDate) dateInput.current?.focus();
  }, [editDate]);

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

  const header = (
    <TopBar title={t("quotesTitle")} back="/vehicule">
      <Stepper current={1} />
    </TopBar>
  );

  if (!quotes && !error) return <App>{header}<Loading /></App>;

  const cheapest = quotes && quotes.length > 1 ? Math.min(...quotes.map((q) => q.premium)) : null;
  const chosen = quotes?.find((q) => q.id === picked);

  return (
    <App>
      {header}
      <main className="content">
        {asset && (
          <div className="row ink2" style={{ gap: 10, fontSize: 14, flexWrap: "wrap" }}>
            <span className="chip"><bdi>{asset.reference}</bdi></span>
            <span>
              {[asset.attributes.make, `${asset.attributes.fiscal_power} CV`, USAGE[String(asset.attributes.usage)] && t(USAGE[String(asset.attributes.usage)])]
                .filter(Boolean)
                .join(" · ")}
            </span>
          </div>
        )}
        {error && <ErrorBox message={error} onRetry={quotes ? undefined : load} />}
        {quotes && quotes.length === 0 && <p className="ink2">{t("noQuotes")}</p>}
        {quotes && quotes.length > 0 && (
          <>
            <div className="stack" role="radiogroup" aria-label={t("quotesTitle")}>
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
                    <div className="row">
                      <span className={`avatar${on ? " on" : ""}`} aria-hidden="true">
                        {on ? <Icon name="check" size={20} strokeWidth={3} /> : initial(q.insurer)}
                      </span>
                      <div className="grow stack" style={{ gap: 2 }}>
                        <strong style={{ fontSize: 16 }}>{q.insurer}</strong>
                        <span className="ink2" style={{ fontSize: 14 }}>{q.product}</span>
                      </div>
                      <div className="stack" style={{ gap: 4, alignItems: "flex-end" }}>
                        <span className="price">{money(q.premium, lang)}</span>
                        {q.premium === cheapest && <span className="badge-sand">{t("cheapest")}</span>}
                      </div>
                    </div>
                    {on && (
                      <div className="grid2" style={{ gap: "6px 10px", fontSize: 14 }}>
                        {q.coverages.map((c) => (
                          <span key={c} className="row" style={{ gap: 6 }}>
                            <Icon name="check" size={16} strokeWidth={2.6} />
                            {c}
                          </span>
                        ))}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
            <span className="small muted" style={{ textAlign: "center" }}>{t("pricesNote")}</span>
          </>
        )}
      </main>
      {quotes && quotes.length > 0 && (
        <div className="footer-cta">
          {editDate ? (
            <div className="field">
              <label htmlFor="start">{t("startsOn")}</label>
              <input id="start" ref={dateInput} className="input" type="date" value={startsOn} onChange={(e) => setStartsOn(e.target.value)} onBlur={() => setEditDate(false)} />
            </div>
          ) : (
            <div className="between" style={{ fontSize: 14 }}>
              <span className="ink2">
                {t("effectOn")} <strong style={{ color: "var(--ink)" }}>{date(startsOn, lang)}</strong>
              </span>
              <button type="button" className="btn link" onClick={() => setEditDate(true)}>{t("edit")}</button>
            </div>
          )}
          <button type="button" className="btn primary block tall split" onClick={proceed} disabled={!picked || busy}>
            <span>{t("continue")}</span>
            {chosen && <span>{money(chosen.premium, lang)}</span>}
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
