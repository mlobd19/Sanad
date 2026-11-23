"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { DURATION_LABEL, DurationPicker, parseMonths } from "@/components/DurationPicker";
import { Icon } from "@/components/Icon";
import { InsurerLogo } from "@/components/InsurerLogo";
import { App, ErrorBox, Loading, Stepper, TopBar } from "@/components/Shell";
import { VehicleIllustration } from "@/components/VehicleIllustration";
import { api, ApiError, type Asset, type Months, type Policy, type Quote } from "@/lib/api";
import { date, formatPlate, money } from "@/lib/format";
import { useI18n, type Key } from "@/lib/i18n";
import { useSpace } from "@/lib/spaces";

const FORMULA_ORDER = ["rc", "tiers-etendu", "tous-risques"];

const USAGE: Record<string, Key> = { personal: "usagePersonal", commercial: "usageCommercial" };

function QuotesScreen() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const { assetId } = useParams<{ assetId: string }>();
  const search = useSearchParams();
  const renewalOf = search.get("renouvellement");
  const { user } = useSpace("customer");
  const [asset, setAsset] = useState<Asset | null>(null);
  const [quotes, setQuotes] = useState<Quote[] | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const [formula, setFormula] = useState<string>("");
  const [months, setMonths] = useState<Months>(parseMonths(search.get("duree")));
  const [loading, setLoading] = useState(false);
  const [startsOn, setStartsOn] = useState(search.get("debut") ?? new Date().toISOString().slice(0, 10));
  const [editDate, setEditDate] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const dateInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (user) api<Asset[]>("assets").then((list) => setAsset(list.find((a) => String(a.id) === assetId) ?? null)).catch(() => undefined);
  }, [user, assetId]);

  // Choix en cours, relu au rechargement des devis (sans relancer leur chargement).
  const choice = useRef({ formula: "", insurer: "" });

  // Nouveaux devis à chaque changement de durée : la formule et la compagnie choisies sont conservées.
  const load = useCallback(() => {
    setError("");
    setLoading(true);
    api<Quote[]>(`assets/${assetId}/quotes`, { body: { months } })
      .then((qs) => {
        const { formula: current, insurer } = choice.current;
        const code = qs.some((q) => q.product_code === current)
          ? current
          : FORMULA_ORDER.find((c) => qs.some((q) => q.product_code === c)) ?? qs[0]?.product_code ?? "";
        const same = qs.find((q) => q.product_code === code && q.insurer_slug === insurer);
        setQuotes(qs);
        setFormula(code);
        setPicked((same ?? qs.find((q) => q.product_code === code))?.id ?? null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [assetId, months]);

  useEffect(() => {
    choice.current = { formula, insurer: quotes?.find((q) => q.id === picked)?.insurer_slug ?? "" };
  }, [formula, picked, quotes]);

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

  const formulas = quotes
    ? [...new Map(quotes.map((q) => [q.product_code, q.product])).entries()].sort(
        ([a], [b]) => (FORMULA_ORDER.indexOf(a) + 1 || 99) - (FORMULA_ORDER.indexOf(b) + 1 || 99),
      )
    : [];
  const shown = (quotes ?? []).filter((q) => q.product_code === formula);
  const prices = shown.map((q) => q.premium);
  const min = Math.min(...prices);
  // « Le moins cher » seulement s'il y a un vrai écart (pas pour la RC, au tarif identique partout).
  const cheapest = shown.length > 1 && prices.filter((p) => p === min).length === 1 ? min : null;
  const chosen = quotes?.find((q) => q.id === picked);

  function chooseFormula(code: string) {
    setFormula(code);
    setPicked((quotes ?? []).find((q) => q.product_code === code)?.id ?? null);
  }

  return (
    <App>
      {header}
      <main className="content">
        {asset && (
          <div className="row ink2" style={{ gap: 12, fontSize: 14 }}>
            <VehicleIllustration type={asset.body_type} width={96} />
            <div className="stack" style={{ gap: 6, alignItems: "flex-start", minWidth: 0 }}>
              <span className="chip"><bdi dir="ltr">{formatPlate(asset.reference)}</bdi></span>
              <span>
                {[asset.attributes.make, `${asset.attributes.fiscal_power} CV`, USAGE[String(asset.attributes.usage)] && t(USAGE[String(asset.attributes.usage)])]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </div>
          </div>
        )}
        {error && <ErrorBox message={error} onRetry={quotes ? undefined : load} />}
        {quotes && quotes.length === 0 && <p className="ink2">{t("noQuotes")}</p>}
        {quotes && quotes.length > 0 && (
          <>
            <DurationPicker value={months} onChange={setMonths} disabled={loading} />
            {months < 12 && <p className="note" style={{ margin: 0 }}>{t("shortTermNote")}</p>}
            <div className="chips" role="group" aria-label={t("formula")}>
              {formulas.map(([code, label]) => (
                <button key={code} type="button" aria-pressed={formula === code} onClick={() => chooseFormula(code)}>
                  {label}
                </button>
              ))}
            </div>
            {formula === "rc" && shown.length > 1 && cheapest === null && (
              <p className="note" style={{ margin: 0 }}>
                <Icon name="shield" size={16} strokeWidth={2} />
                {t("rcRegulated")}
              </p>
            )}
            <div className="stack" role="radiogroup" aria-label={t("quotesTitle")} aria-busy={loading}
              style={loading ? { opacity: 0.5, pointerEvents: "none" } : undefined}>
              {shown.map((q) => {
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
                      <InsurerLogo name={q.insurer} logo={q.insurer_logo} size={48} selected={on} />
                      <div className="grow stack" style={{ gap: 2 }}>
                        <strong style={{ fontSize: 16 }}>{q.insurer}</strong>
                        {q.insurer_legal_name && q.insurer_legal_name !== q.insurer && (
                          <span className="ink2" style={{ fontSize: 13 }}>{q.insurer_legal_name}</span>
                        )}
                      </div>
                      <div className="stack" style={{ gap: 4, alignItems: "flex-end" }}>
                        <span className="price">{money(q.premium, lang)}</span>
                        {q.premium === cheapest && <span className="badge-sand">{t("cheapest")}</span>}
                        {q.indicative && <span className="small muted">{t("indicative")}</span>}
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
            <span className="small muted" style={{ textAlign: "center" }}>{t("pricesNote", { duration: t(DURATION_LABEL[months]) })}</span>
            {quotes.some((q) => q.indicative) && (
              <p className="note" style={{ margin: 0, justifyContent: "center", textAlign: "center" }}>{t("indicativeNote")}</p>
            )}
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
                {t("effectOn")} <strong style={{ color: "var(--ink)" }}>{date(startsOn, lang)}</strong> · {t(DURATION_LABEL[months])}
              </span>
              <button type="button" className="btn link" onClick={() => setEditDate(true)}>{t("edit")}</button>
            </div>
          )}
          <button type="button" className="btn primary block tall split" onClick={proceed} disabled={!picked || busy || loading}>
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
