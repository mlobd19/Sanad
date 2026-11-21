"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";

import { ClaimForm } from "@/components/ClaimForm";
import { DURATION_LABEL, DurationPicker } from "@/components/DurationPicker";
import { InsurerLogo } from "@/components/InsurerLogo";
import { ThemeToggleButton } from "@/components/ThemeChoice";
import { ScanRegistration } from "@/components/ScanRegistration";
import { VehicleIllustration } from "@/components/VehicleIllustration";
import {
  api,
  ApiError,
  apiUpload,
  downloadFile,
  type CompanyMe,
  type CompanyMember,
  type CompanyOrder,
  type FleetClaim,
  type FleetImport,
  type GroupOffer,
  type Months,
  type PaymentStart,
  type Policy,
  type Provider,
  type RegistrationScan,
  type Vehicle,
} from "@/lib/api";
import { cleanPlate, date, daysUntil, formatPlate, money, num, plateInput } from "@/lib/format";
import { useI18n, type Key } from "@/lib/i18n";
import { logout as signOut, useSpace } from "@/lib/spaces";
import { useLoad } from "@/lib/useLoad";

type Tab = "fleet" | "quotes" | "contracts" | "claims" | "company";

const TABS: { id: Tab; label: Key }[] = [
  { id: "fleet", label: "tabFleet" },
  { id: "quotes", label: "tabQuotes" },
  { id: "contracts", label: "tabContracts" },
  { id: "claims", label: "tabClaims" },
  { id: "company", label: "tabCompany" },
];

const USAGE: Record<string, Key> = { personal: "usagePersonal", commercial: "usageCommercial", taxi: "usageTaxi" };
const STATUS_PILL: Record<string, string> = { active: "pill", refused: "pill bad", paid: "pill warn", draft: "pill quiet" };
const COMPANY_PILL: Record<string, string> = { verified: "pill", pending: "pill warn", rejected: "pill bad" };
const CLAIM_PILL: Record<string, string> = { submitted: "pill warn", in_review: "pill warn", closed: "pill quiet" };
/** Un sinistre se déclare sur un contrat en cours ou échu. */
const claimable = (p: Policy) => p.status === "active" || p.status === "expired";

function message(err: unknown, fallback: string) {
  return err instanceof ApiError ? err.message : fallback;
}

// --- Page -------------------------------------------------------------------------------------

export default function CompanySpacePage() {
  const { t } = useI18n();
  // Garde-fou commun : non connecté → /connexion (onglet pro) ; autre rôle → son propre espace.
  const { user } = useSpace("company_member");
  const [me, setMe] = useState<CompanyMe | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  async function load() {
    try {
      setMe(await api<CompanyMe>("company/me"));
      setState("ready");
    } catch {
      setState("error");
    }
  }

  useEffect(() => {
    if (user) load();
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  if (state === "ready" && me) return <Space me={me} refreshMe={load} />;

  return (
    <div className="portal-login">
      <div className="box">
        <main className="sheet center" style={{ color: "var(--ink)", minHeight: 280 }}>
          {state === "loading" && <span className="spinner" aria-label={t("loading")} />}
          {state === "error" && (
            <>
              <p className="error" role="alert">{t("error")}</p>
              <button type="button" className="btn primary" onClick={() => window.location.reload()}>{t("retry")}</button>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function Space({ me, refreshMe }: { me: CompanyMe; refreshMe: () => Promise<void> }) {
  const { t, lang, setLang } = useI18n();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("fleet");
  const [selection, setSelection] = useState<number[]>([]);
  // Contrat choisi dans « Contrats » pour déclarer un sinistre (ouvre le formulaire de l'onglet « Sinistres »).
  const [declareFor, setDeclareFor] = useState<number | null>(null);
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({
    fleet: null, quotes: null, contracts: null, claims: null, company: null,
  });
  const { company, member } = me;

  useEffect(() => {
    // Après l'inscription : ouvrir directement l'onglet « Entreprise » (dépôt des pièces).
    if (new URLSearchParams(window.location.search).get("onglet") === "entreprise") setTab("company");
  }, []);

  function logout() {
    signOut(router, "company_member");
  }

  function onTabKey(e: KeyboardEvent<HTMLButtonElement>) {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    if (!step) return;
    e.preventDefault();
    const rtl = document.documentElement.dir === "rtl";
    const i = TABS.findIndex((x) => x.id === tab);
    const next = TABS[(i + (rtl ? -step : step) + TABS.length) % TABS.length].id;
    setTab(next);
    tabRefs.current[next]?.focus();
  }

  return (
    <div className="portal">
      <header className="portal-head">
        <div className="portal-wrap">
          <InsurerLogo name={company.legal_name} size={56} />
          <div className="grow">
            <h1>{company.legal_name}</h1>
            <div className="sub row" style={{ gap: 10, flexWrap: "wrap" }}>
              <span><bdi dir="ltr">{t("nifShort", { nif: company.nif })}</bdi> · {t("companySpace")} {t("appName")}</span>
              <span className={COMPANY_PILL[company.status]}>{t(`companyStatus_${company.status}`)}</span>
            </div>
          </div>
          <div className="agent">
            <strong><bdi>{member.full_name || member.email}</bdi></strong>
            <span>{t(member.role === "admin" ? "roleAdmin" : "roleManager")}</span>
          </div>
          <button type="button" className="btn-on-dark" onClick={() => setLang(lang === "fr" ? "ar" : "fr")}>
            {lang === "fr" ? "العربية" : "Français"}
          </button>
          <ThemeToggleButton />
          <button type="button" className="btn-on-dark" onClick={logout}>{t("logout")}</button>
        </div>
      </header>

      <nav className="portal-tabs">
        <div className="portal-wrap" role="tablist" aria-label={t("companySections")}>
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              ref={(el) => { tabRefs.current[id] = el; }}
              type="button"
              role="tab"
              id={`tab-${id}`}
              aria-selected={tab === id}
              aria-controls={`panel-${id}`}
              tabIndex={tab === id ? 0 : -1}
              onClick={() => setTab(id)}
              onKeyDown={onTabKey}
            >
              {t(label)}
              {id === "quotes" && selection.length > 0 && <span className="count">{num(selection.length, lang)}</span>}
              {id === "company" && company.missing_documents.length > 0 && <span className="count">!</span>}
            </button>
          ))}
        </div>
      </nav>

      <main className="portal-wrap portal-main" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        <StatusBanner me={me} onOpenCompany={() => setTab("company")} />
        {tab === "fleet" && (
          <FleetTab selection={selection} setSelection={setSelection} onCompare={() => setTab("quotes")} />
        )}
        {tab === "quotes" && (
          <QuotesTab selection={selection} verified={company.status === "verified"}
            onBackToFleet={() => setTab("fleet")}
            onPaid={() => { setSelection([]); setTab("contracts"); }} />
        )}
        {tab === "contracts" && <ContractsTab onDeclare={(id) => { setDeclareFor(id); setTab("claims"); }} />}
        {tab === "claims" && <ClaimsTab declareFor={declareFor} setDeclareFor={setDeclareFor} />}
        {tab === "company" && <CompanyTab me={me} refreshMe={refreshMe} />}
      </main>
    </div>
  );
}

function StatusBanner({ me, onOpenCompany }: { me: CompanyMe; onOpenCompany: () => void }) {
  const { t } = useI18n();
  const { company } = me;
  if (company.status === "verified") return null;
  if (company.status === "rejected") {
    return (
      <div className="banner red" role="status">
        <span className="grow"><strong>{t("bannerRejected", { reason: company.rejection_reason })}</strong></span>
        <button type="button" className="btn link" onClick={onOpenCompany}>{t("goToCompanyTab")}</button>
      </div>
    );
  }
  return (
    <div className="banner sand" role="status">
      <span className="grow">
        <strong>{t("bannerPending")}</strong>
        {company.missing_documents.length > 0 && <> {t("bannerMissingDocs")}</>}
      </span>
      {company.missing_documents.length > 0 && (
        <button type="button" className="btn link" onClick={onOpenCompany}>{t("goToCompanyTab")}</button>
      )}
    </div>
  );
}

function SectionHead({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="between" style={{ flexWrap: "wrap" }}>
      <h2>{title}</h2>
      {children && <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>{children}</div>}
    </div>
  );
}

function Indicative({ on }: { on: boolean }) {
  const { t } = useI18n();
  return on ? <span className="badge-sand" style={{ display: "inline-block", marginTop: 4 }}>{t("indicative")}</span> : null;
}

function vehicleDetails(v: Vehicle["attributes"], t: (k: Key, vars?: Record<string, string | number>) => string,
  lang: "fr" | "ar") {
  return [
    v.make ?? "",
    v.fiscal_power ? t("cvShort", { n: num(v.fiscal_power, lang) }) : "",
    v.usage && USAGE[v.usage] ? t(USAGE[v.usage]) : v.usage ?? "",
  ].filter(Boolean);
}

// --- Onglet « Flotte » ---------------------------------------------------------------------------

function FleetTab({ selection, setSelection, onCompare }: {
  selection: number[]; setSelection: (ids: number[]) => void; onCompare: () => void;
}) {
  const { t, lang } = useI18n();
  const { data, error, reload } = useLoad<Vehicle[]>("company/fleet");
  const selectable = (v: Vehicle) => !v.policy || !["active", "paid"].includes(v.policy.status);
  const choices = (data ?? []).filter(selectable).map((v) => v.id);
  const all = choices.length > 0 && choices.every((id) => selection.includes(id));

  function toggle(id: number) {
    setSelection(selection.includes(id) ? selection.filter((x) => x !== id) : [...selection, id]);
  }

  return (
    <>
      <SectionHead title={t("fleetTitle")}>
        <button type="button" className="btn outline" onClick={reload}>{t("refresh")}</button>
      </SectionHead>
      <div className="two-cols">
        <AddVehicleCard onAdded={reload} />
        <ImportCard onImported={reload} />
      </div>
      {error && <div className="banner red" role="alert">{error === "error" ? t("error") : error}</div>}
      {!data && !error && <div className="center" style={{ minHeight: 160 }}><span className="spinner" aria-label={t("loading")} /></div>}
      {data && data.length === 0 && <div className="card"><p className="ink2" style={{ margin: 0 }}>{t("noVehicles")}</p></div>}
      {data && data.length > 0 && (
        <div className="ptable-wrap">
          <table className="ptable">
            <thead>
              <tr>
                <th scope="col" style={{ width: 52 }}>
                  <input type="checkbox" className="check" checked={all} aria-label={t("selectAll")}
                    onChange={() => setSelection(all ? [] : choices)} disabled={choices.length === 0} />
                </th>
                <th scope="col">{t("plate")}</th>
                <th scope="col">{t("vehicle")}</th>
                <th scope="col">{t("colCurrentContract")}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((v) => (
                <tr key={v.id} className={selection.includes(v.id) ? "selected" : undefined}>
                  <td className="act">
                    <input type="checkbox" className="check" checked={selection.includes(v.id)} disabled={!selectable(v)}
                      onChange={() => toggle(v.id)} aria-label={t("selectVehicle", { plate: formatPlate(v.reference) })} />
                  </td>
                  <td data-label={t("plate")}>
                    <span className="row" style={{ gap: 10 }}>
                      <VehicleIllustration type={v.body_type} width={64} />
                      <bdi className="plate" dir="ltr">{formatPlate(v.reference)}</bdi>
                    </span>
                  </td>
                  <td data-label={t("vehicle")}>
                    {vehicleDetails(v.attributes, t, lang).map((d, i) => (
                      <span key={i}>{i > 0 && " · "}<bdi>{d}</bdi></span>
                    ))}
                  </td>
                  <td data-label={t("colCurrentContract")}>
                    {v.policy ? (
                      <>
                        <span className={STATUS_PILL[v.policy.status] ?? "pill quiet"}>{t(`status_${v.policy.status}`)}</span>
                        <span className="sub">{v.policy.insurer} · {v.policy.product} · {t("expiresShort", { date: date(v.policy.ends_on, lang) })}</span>
                      </>
                    ) : <span className="muted">{t("noContract")}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selection.length > 0 && (
        <div className="actionbar" role="region" aria-label={t("selectedCount", { count: num(selection.length, lang) })}>
          <strong>{t("selectedCount", { count: num(selection.length, lang) })}</strong>
          <div className="row" style={{ gap: 8 }}>
            <button type="button" className="btn outline" onClick={() => setSelection([])}>{t("clearSelection")}</button>
            <button type="button" className="btn primary" onClick={onCompare}>{t("compareOffers")}</button>
          </div>
        </div>
      )}
    </>
  );
}

function AddVehicleCard({ onAdded }: { onAdded: () => void }) {
  const { t } = useI18n();
  const [plate, setPlate] = useState("");
  const [make, setMake] = useState("");
  const [power, setPower] = useState("");
  const [usage, setUsage] = useState("personal");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("company/fleet", { body: { reference: cleanPlate(plate), attributes: { make, fiscal_power: power, usage } } });
      setPlate("");
      setMake("");
      setPower("");
      onAdded();
    } catch (err) {
      setError(message(err, t("error")));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h3 className="card-title">{t("addVehicleTitle")}</h3>
      <ScanRegistration onRead={(f: RegistrationScan) => {
        if (f.reference) setPlate(plateInput(f.reference));
        if (f.make) setMake(f.make);
        if (f.fiscal_power) setPower(String(f.fiscal_power));
      }} />
      <div className="form-grid">
        <div className="field">
          <label htmlFor="v-plate">{t("plate")}</label>
          <input id="v-plate" className="input plate-input" dir="ltr" value={plate} onChange={(e) => setPlate(plateInput(e.target.value))}
            required autoCapitalize="characters" autoComplete="off" spellCheck={false} placeholder="66 02 BA 00" />
        </div>
        <div className="field">
          <label htmlFor="v-make">{t("make")}</label>
          <input id="v-make" className="input" value={make} onChange={(e) => setMake(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="v-power">{t("fiscalPower")}</label>
          <input id="v-power" className="input" type="number" inputMode="numeric" min={1} max={60} value={power}
            onChange={(e) => setPower(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="v-usage">{t("usage")}</label>
          <select id="v-usage" className="input" value={usage} onChange={(e) => setUsage(e.target.value)}>
            {Object.entries(USAGE).map(([code, key]) => <option key={code} value={code}>{t(key)}</option>)}
          </select>
        </div>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <button className="btn primary" disabled={busy || !plate || !power} style={{ alignSelf: "flex-start" }}>
        {busy ? <span className="spinner sm" /> : t("addVehicleBtn")}
      </button>
    </form>
  );
}

function ImportCard({ onImported }: { onImported: () => void }) {
  const { t, lang } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<FleetImport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      setResult(await apiUpload<FleetImport>("company/fleet/import", form));
      onImported();
    } catch (err) {
      setError(message(err, t("error")));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h3 className="card-title">{t("importTitle")}</h3>
      <p className="ink2 small" style={{ margin: 0 }}>{t("importHint")}</p>
      <code className="csv-sample" dir="ltr">immatriculation;marque;cv;usage<br />1234AB00;Toyota Hilux;9;commercial</code>
      <div className="field">
        <label htmlFor="v-file">{t("importFile")}</label>
        <input id="v-file" className="input file" type="file" accept=".csv,text/csv"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {result && (
        <div className="stack" role="status" style={{ gap: 6 }}>
          <div className={`banner ${result.errors.length ? "sand" : "green"}`}>
            <strong>{t("importResult", { count: num(result.created.length, lang) })}</strong>
          </div>
          {result.errors.length > 0 && (
            <ul className="import-errors">
              {result.errors.map((e) => (
                <li key={e.line}><strong>{t("lineN", { line: num(e.line, lang) })}</strong>
                  {e.plate && <> · <bdi dir="ltr">{formatPlate(e.plate)}</bdi></>} : {e.message}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      <button className="btn outline" disabled={busy || !file} style={{ alignSelf: "flex-start" }}>
        {busy ? <span className="spinner sm" /> : t("importBtn")}
      </button>
    </form>
  );
}

// --- Onglet « Offres » ----------------------------------------------------------------------------

function QuotesTab({ selection, verified, onBackToFleet, onPaid }: {
  selection: number[]; verified: boolean; onBackToFleet: () => void; onPaid: () => void;
}) {
  const { t, lang } = useI18n();
  const [offers, setOffers] = useState<GroupOffer[] | null>(null);
  const [formula, setFormula] = useState("all");
  const [order, setOrder] = useState<CompanyOrder | null>(null);
  const [startsOn, setStartsOn] = useState(new Date().toISOString().slice(0, 10));
  const [months, setMonths] = useState<Months>(12);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = selection.join(",");

  useEffect(() => {
    if (!key) return;
    setOffers(null);
    setOrder(null);
    setError("");
    api<GroupOffer[]>("company/quotes", { body: { asset_ids: key.split(",").map(Number), months } })
      .then(setOffers)
      .catch((err) => setError(message(err, t("error"))));
  }, [key, months]); // eslint-disable-line react-hooks/exhaustive-deps

  async function orderOffer(offer: GroupOffer) {
    setBusy(true);
    setError("");
    try {
      setOrder(await api<CompanyOrder>("company/orders", {
        body: { quote_ids: offer.lines.map((l) => l.quote_id), starts_on: startsOn },
      }));
    } catch (err) {
      setError(message(err, t("error")));
    } finally {
      setBusy(false);
    }
  }

  if (!selection.length) {
    return (
      <>
        <SectionHead title={t("tabQuotes")} />
        <div className="card">
          <p className="ink2" style={{ margin: 0 }}>{t("noSelection")}</p>
          <button type="button" className="btn primary" style={{ alignSelf: "flex-start" }} onClick={onBackToFleet}>{t("tabFleet")}</button>
        </div>
      </>
    );
  }

  if (order) return <OrderPayment order={order} verified={verified} onPaid={onPaid} onCancel={() => setOrder(null)} />;

  const formulas = Array.from(new Map((offers ?? []).map((o) => [o.product_code, o.product])).entries());
  const shown = (offers ?? []).filter((o) => formula === "all" || o.product_code === formula);
  const cheapest = shown.length ? Math.min(...shown.map((o) => o.total)) : null;

  return (
    <>
      <SectionHead title={t("offersFor", { count: num(selection.length, lang) })}>
        <div className="field" style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <label htmlFor="starts-on">{t("startsOn")}</label>
          <input id="starts-on" className="input" type="date" value={startsOn} style={{ height: 44, width: "auto" }}
            onChange={(e) => setStartsOn(e.target.value)} />
        </div>
      </SectionHead>
      <DurationPicker value={months} onChange={setMonths} disabled={!offers && !error} />
      {months < 12 && <p className="note" style={{ margin: 0 }}>{t("shortTermNote")}</p>}
      <p className="note" style={{ margin: 0 }}>{t("indicativeNote")}</p>
      {error && <div className="banner red" role="alert">{error}</div>}
      {!offers && !error && <div className="center" style={{ minHeight: 160 }}><span className="spinner" aria-label={t("loading")} /></div>}
      {offers && offers.length > 0 && (
        <div className="chips" role="group" aria-label={t("formula")}>
          <button type="button" aria-pressed={formula === "all"} onClick={() => setFormula("all")}>{t("allFormulas")}</button>
          {formulas.map(([code, label]) => (
            <button key={code} type="button" aria-pressed={formula === code} onClick={() => setFormula(code)}>{label}</button>
          ))}
        </div>
      )}
      {formula === "rc" && <p className="note" style={{ margin: 0 }}>{t("rcRegulated")}</p>}
      <div className="offers">
        {shown.map((o) => (
          <article key={`${o.insurer}-${o.product_code}`} className="card offer">
            <div className="row">
              <InsurerLogo name={o.insurer} logo={o.insurer_logo} size={48} />
              <div className="grow stack" style={{ gap: 2 }}>
                <strong style={{ fontSize: 16 }}>{o.insurer} · {o.product}</strong>
                {o.insurer_legal_name !== o.insurer && <span className="ink2 small">{o.insurer_legal_name}</span>}
              </div>
              <div className="stack" style={{ gap: 4, alignItems: "flex-end" }}>
                <span className="price">{money(o.total, lang)}</span>
                <span className="small muted">{t(DURATION_LABEL[o.duration_months])}</span>
                {o.total === cheapest && formula !== "rc" && <span className="badge-sand">{t("cheapest")}</span>}
                <Indicative on={o.indicative} />
              </div>
            </div>
            <p className="small ink2" style={{ margin: 0 }}>{o.coverages.join(" · ")}</p>
            <details>
              <summary>{t("perVehicle")}</summary>
              <table className="mini">
                <tbody>
                  {o.lines.map((l) => (
                    <tr key={l.asset_id}><td><bdi dir="ltr">{formatPlate(l.plate)}</bdi></td><td className="num">{money(l.premium, lang)}</td></tr>
                  ))}
                </tbody>
              </table>
            </details>
            <button type="button" className="btn primary" disabled={busy} onClick={() => orderOffer(o)}
              aria-label={`${t("orderOffer")} · ${o.insurer} · ${o.product}`}>
              {t("orderOffer")}
            </button>
          </article>
        ))}
      </div>
    </>
  );
}

function OrderPayment({ order, verified, onPaid, onCancel }: {
  order: CompanyOrder; verified: boolean; onPaid: () => void; onCancel: () => void;
}) {
  const { t, lang } = useI18n();
  const { data: providers } = useLoad<Provider[]>("payments/providers");
  const [provider, setProvider] = useState("");
  const [payer, setPayer] = useState("");
  const [payment, setPayment] = useState<PaymentStart | null>(null);
  const [paid, setPaid] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function pay() {
    setBusy(true);
    setError("");
    try {
      setPayment(await api<PaymentStart>(`company/orders/${order.id}/pay`, { body: { provider, payer_phone: payer } }));
    } catch (err) {
      setError(message(err, t("error")));
    } finally {
      setBusy(false);
    }
  }

  async function check() {
    const fresh = await api<CompanyOrder>(`company/orders/${order.id}`);
    if (fresh.policies.every((p) => p.status !== "draft")) setPaid(true);
  }

  async function simulate() {
    if (!payment) return;
    setBusy(true);
    try {
      await api(`payments/${payment.payment_id}/simulate-confirm`, { method: "POST" });
      await check();
    } catch (err) {
      setError(message(err, t("error")));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <SectionHead title={t("orderTitle", { id: num(order.id, lang) })} />
      <div className="two-cols">
        <section className="card" aria-label={t("summary")}>
          <h3 className="card-title">{t("summary")}</h3>
          <table className="mini">
            <tbody>
              {order.policies.map((p) => (
                <tr key={p.id}>
                  <td><bdi dir="ltr">{formatPlate(p.plate)}</bdi><span className="sub">{p.insurer} · {p.product}</span></td>
                  <td className="num">{money(p.premium, lang)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="amount-card">
            <span className="sub">{t("total")}</span>
            <span className="big">{money(order.total, lang)}</span>
          </div>
        </section>

        <section className="card" aria-label={t("payTitle")}>
          <h3 className="card-title">{t("payTitle")}</h3>
          {paid ? (
            <>
              <div className="banner green" role="status"><strong>{t("orderPaid")}</strong></div>
              <button type="button" className="btn primary" onClick={onPaid}>{t("seeContracts")}</button>
            </>
          ) : !verified ? (
            <div className="banner sand" role="status"><strong>{t("payBlocked")}</strong></div>
          ) : payment ? (
            <div className="wait-card">
              <strong>{t("confirmOnPhone")}</strong>
              <span className="small ink2">{t("pendingRef")} <bdi dir="ltr">{payment.reference}</bdi></span>
              {provider === "simulated" && (
                <button type="button" className="btn outline block" onClick={simulate} disabled={busy}>{t("simulate")}</button>
              )}
              <button type="button" className="btn outline block" onClick={() => check().catch(() => undefined)} disabled={busy}>
                {t("iPaid")}
              </button>
            </div>
          ) : (
            <>
              <div className="stack" role="radiogroup" aria-label={t("method")}>
                {(providers ?? []).map((p) => (
                  <button key={p.code} type="button" role="radio" aria-checked={provider === p.code} className="radio"
                    onClick={() => setProvider(p.code)}>
                    {p.label}<span className="dot" />
                  </button>
                ))}
              </div>
              <div className="field">
                <label htmlFor="payer">{t("payerPhone")}</label>
                <input id="payer" className="input" type="tel" dir="ltr" value={payer} onChange={(e) => setPayer(e.target.value)} />
              </div>
              <button type="button" className="btn primary block tall" onClick={pay} disabled={busy || !provider}>
                {t("pay", { amount: money(order.total, lang) })}
              </button>
            </>
          )}
          {error && <p className="error" role="alert">{error}</p>}
          {!payment && !paid && <button type="button" className="btn link" onClick={onCancel}>{t("backToOffers")}</button>}
        </section>
      </div>
    </>
  );
}

// --- Onglet « Contrats » ------------------------------------------------------------------------

function ContractsTab({ onDeclare }: { onDeclare: (policyId: number) => void }) {
  const { t, lang } = useI18n();
  const { data, error, reload } = useLoad<Policy[]>("company/policies");
  const [busy, setBusy] = useState("");
  const [dlError, setDlError] = useState("");

  async function download(path: string, filename: string, id: string) {
    setBusy(id);
    setDlError("");
    try {
      await downloadFile(path, filename);
    } catch (err) {
      setDlError(message(err, t("error")));
    } finally {
      setBusy("");
    }
  }

  const rows = (data ?? []).filter((p) => p.status !== "draft");
  const hasValid = rows.some((p) => p.status === "active" && p.attestation);

  return (
    <>
      <SectionHead title={t("tabContracts")}>
        <button type="button" className="btn outline" onClick={reload}>{t("refresh")}</button>
        <button type="button" className="btn primary" disabled={!hasValid || busy === "zip"}
          onClick={() => download("company/attestations.zip", "attestations.zip", "zip")}>
          {busy === "zip" ? <span className="spinner sm" /> : t("downloadZip")}
        </button>
      </SectionHead>
      <p className="note" style={{ margin: 0 }}>{t("indicativeNote")}</p>
      {dlError && <div className="banner red" role="alert">{dlError}</div>}
      {error && <div className="banner red" role="alert">{error === "error" ? t("error") : error}</div>}
      {!data && !error && <div className="center" style={{ minHeight: 160 }}><span className="spinner" aria-label={t("loading")} /></div>}
      {data && rows.length === 0 && <div className="card"><p className="ink2" style={{ margin: 0 }}>{t("companyNoContracts")}</p></div>}
      {rows.length > 0 && (
        <div className="ptable-wrap">
          <table className="ptable">
            <thead>
              <tr>
                <th scope="col">{t("plate")}</th>
                <th scope="col">{t("insurer")}</th>
                <th scope="col">{t("colPremium")}</th>
                <th scope="col">{t("colStatus")}</th>
                <th scope="col">{t("period")}</th>
                <th scope="col">{t("colAttestation")}</th>
                <th scope="col"><span className="sr-only">{t("colActions")}</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => {
                const left = daysUntil(p.ends_on);
                return (
                  <tr key={p.id}>
                    <td data-label={t("plate")}><bdi className="plate" dir="ltr">{formatPlate(p.plate)}</bdi></td>
                    <td data-label={t("insurer")}><strong>{p.insurer}</strong><span className="sub">{p.product}</span></td>
                    <td data-label={t("colPremium")}><strong className="num">{money(p.premium, lang)}</strong></td>
                    <td data-label={t("colStatus")}>
                      <span className={STATUS_PILL[p.status] ?? "pill quiet"}>{t(`status_${p.status}`)}</span>
                      {p.status === "refused" && p.refusal_reason && <span className="sub">{p.refusal_reason}</span>}
                      {p.status === "active" && left <= 30 && <span className="sub due">{t("dueIn", { days: num(left, lang) })}</span>}
                    </td>
                    <td data-label={t("period")} className="num">
                      {date(p.starts_on, lang)}<span className="sub">{t("validTo")} {date(p.ends_on, lang)}</span>
                    </td>
                    <td data-label={t("colAttestation")} className="num">
                      <bdi dir="ltr">{p.attestation?.number ?? "—"}</bdi>
                      {p.attestation && p.status === "active" && (
                        <button type="button" className="btn outline small-btn" disabled={busy === `pdf-${p.id}`}
                          aria-label={t("pdfOf", { number: p.attestation.number })}
                          onClick={() => download(`attestations/${p.attestation!.id}/pdf`, `attestation-${p.attestation!.number}.pdf`, `pdf-${p.id}`)}>
                          {busy === `pdf-${p.id}` ? <span className="spinner sm" /> : t("pdf")}
                        </button>
                      )}
                    </td>
                    <td data-label={t("colActions")}>
                      {claimable(p) && (
                        <button type="button" className="btn outline small-btn" onClick={() => onDeclare(p.id)}
                          aria-label={t("declareClaimFor", { plate: formatPlate(p.plate) })}>
                          {t("declareClaim")}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

// --- Onglet « Sinistres » ----------------------------------------------------------------------

function ClaimsTab({ declareFor, setDeclareFor }: {
  declareFor: number | null; setDeclareFor: (id: number | null) => void;
}) {
  const { t, lang } = useI18n();
  const { data, error, reload } = useLoad<FleetClaim[]>("company/claims");
  const { data: policies } = useLoad<Policy[]>("company/policies");
  const [declaring, setDeclaring] = useState(declareFor !== null);
  const [sent, setSent] = useState<FleetClaim | null>(null);

  const eligible = (policies ?? []).filter(claimable).sort((a, b) => a.plate.localeCompare(b.plate));
  const chosen = eligible.find((p) => p.id === declareFor) ?? null;

  function start() {
    setSent(null);
    setDeclaring(true);
  }

  function stop() {
    setDeclaring(false);
    setDeclareFor(null);
  }

  return (
    <>
      <SectionHead title={t("tabClaims")}>
        <button type="button" className="btn outline" onClick={reload}>{t("refresh")}</button>
        {!declaring && <button type="button" className="btn primary" onClick={start}>{t("declareClaim")}</button>}
      </SectionHead>

      {sent && (
        <div className="banner green" role="status">
          {t("claimSent", { number: sent.number, insurer: sent.insurer })}
        </div>
      )}

      {declaring && (
        <section className="card" aria-labelledby="declare-title" style={{ maxWidth: 560 }}>
          <h3 id="declare-title" style={{ margin: 0 }}>{t("declareClaim")}</h3>
          {policies && eligible.length === 0 && <p className="ink2" style={{ margin: 0 }}>{t("fleetNoClaimable")}</p>}
          {eligible.length > 0 && (
            <div className="field">
              <label htmlFor="claim-vehicle">{t("claimVehicle")}</label>
              <select id="claim-vehicle" className="input" value={chosen?.id ?? ""}
                onChange={(e) => setDeclareFor(e.target.value ? Number(e.target.value) : null)}>
                <option value="">{t("claimPickVehicle")}</option>
                {eligible.map((p) => (
                  <option key={p.id} value={p.id}>
                    {formatPlate(p.plate)} · {p.insurer} · {p.product}{p.status === "expired" ? ` (${t("status_expired")})` : ""}
                  </option>
                ))}
              </select>
            </div>
          )}
          {chosen ? (
            <ClaimForm<FleetClaim> key={chosen.id} policy={chosen} endpoint={`company/policies/${chosen.id}/claims`}
              onCancel={stop}
              onSent={(claim) => { setSent(claim); stop(); reload(); }} />
          ) : (
            <button type="button" className="btn outline" style={{ alignSelf: "flex-start" }} onClick={stop}>{t("cancel")}</button>
          )}
        </section>
      )}

      {error && <div className="banner red" role="alert">{error === "error" ? t("error") : error}</div>}
      {!data && !error && <div className="center" style={{ minHeight: 160 }}><span className="spinner" aria-label={t("loading")} /></div>}
      {data && data.length === 0 && <div className="card"><p className="ink2" style={{ margin: 0 }}>{t("fleetNoClaims")}</p></div>}
      {data && data.length > 0 && (
        <div className="ptable-wrap">
          <table className="ptable">
            <thead>
              <tr>
                <th scope="col">{t("colClaim")}</th>
                <th scope="col">{t("vehicle")}</th>
                <th scope="col">{t("colOccurred")}</th>
                <th scope="col">{t("colStatus")}</th>
                <th scope="col">{t("claimInsurerNote")}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.id}>
                  <td data-label={t("colClaim")}>
                    <strong><bdi dir="ltr">{c.number}</bdi></strong>
                    <span className="sub">{t(`claimKind_${c.kind}` as Key)}</span>
                    {c.declared_by && <span className="sub">{t("declaredBy", { name: c.declared_by })}</span>}
                  </td>
                  <td data-label={t("vehicle")}>
                    <bdi className="plate" dir="ltr">{formatPlate(c.plate)}</bdi>
                    <span className="sub">{c.insurer}</span>
                  </td>
                  <td data-label={t("colOccurred")} className="num">
                    {date(c.occurred_on, lang)}
                    <span className="sub">{c.place}</span>
                  </td>
                  <td data-label={t("colStatus")}>
                    <span className={CLAIM_PILL[c.status]}>{t(`claimStatus_${c.status}` as Key)}</span>
                    {c.injuries && <span className="sub">{t("injuriesFlag")}</span>}
                    {c.photos > 0 && <span className="sub">{t("claimPhotoCount", { n: num(c.photos, lang) })}</span>}
                  </td>
                  <td data-label={t("claimInsurerNote")} style={{ maxWidth: 320 }}>
                    {c.closing_note || <span className="muted">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

// --- Onglet « Entreprise » ---------------------------------------------------------------------

function CompanyTab({ me, refreshMe }: { me: CompanyMe; refreshMe: () => Promise<void> }) {
  const { t, lang } = useI18n();
  const { company, member } = me;
  const admin = member.role === "admin";

  return (
    <>
      <SectionHead title={t("tabCompany")} />
      <div className="two-cols">
        <section className="card" aria-labelledby="company-info">
          <h3 className="card-title" id="company-info">{t("companyInfo")}</h3>
          <dl className="facts">
            <div><dt>{t("legalName")}</dt><dd>{company.legal_name}</dd></div>
            <div><dt>{t("nifLabel")}</dt><dd><bdi dir="ltr">{company.nif}</bdi></dd></div>
            <div><dt>{t("rcLabel")}</dt><dd><bdi dir="ltr">{company.rc_number}</bdi></dd></div>
            {company.address && <div><dt>{t("addressLabel")}</dt><dd>{company.address}</dd></div>}
            <div><dt>{t("colStatus")}</dt><dd><span className={COMPANY_PILL[company.status]}>{t(`companyStatus_${company.status}`)}</span></dd></div>
          </dl>
        </section>
        <section className="card" aria-labelledby="company-docs">
          <h3 className="card-title" id="company-docs">{t("documentsTitle")}</h3>
          <p className="ink2 small" style={{ margin: 0 }}>{t("docHint")}</p>
          {(["nif", "rc"] as const).map((kind) => {
            const doc = company.documents.find((d) => d.kind === kind);
            return (
              <DocumentRow key={kind} kind={kind} uploadedAt={doc?.uploaded_at} canUpload={admin} onUploaded={refreshMe}
                lang={lang} />
            );
          })}
        </section>
      </div>
      <MembersCard admin={admin} />
    </>
  );
}

function DocumentRow({ kind, uploadedAt, canUpload, onUploaded, lang }: {
  kind: "nif" | "rc"; uploadedAt?: string; canUpload: boolean; onUploaded: () => Promise<void>; lang: "fr" | "ar";
}) {
  const { t } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const label = t(kind === "nif" ? "docNif" : "docRc");

  async function upload() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("kind", kind);
      form.append("file", file);
      await apiUpload(`company/documents`, form);
      setFile(null);
      await onUploaded();
    } catch (err) {
      setError(message(err, t("error")));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="doc-row">
      <div className="grow">
        <strong>{label}</strong>
        <span className="sub">
          {uploadedAt ? t("docUploaded", { date: date(uploadedAt, lang) }) : <span className="due">{t("docMissing")}</span>}
        </span>
      </div>
      {canUpload && (
        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          <input id={`doc-${kind}`} className="input file" type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
            aria-label={`${label} · ${t("uploadDoc")}`} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <button type="button" className="btn outline" disabled={!file || busy} onClick={upload}>
            {busy ? <span className="spinner sm" /> : t("uploadDoc")}
          </button>
        </div>
      )}
      {error && <p className="error" role="alert" style={{ flexBasis: "100%" }}>{error}</p>}
    </div>
  );
}

function MembersCard({ admin }: { admin: boolean }) {
  const { t } = useI18n();
  const { data, reload } = useLoad<CompanyMember[]>("company/members");
  const [form, setForm] = useState({ full_name: "", email: "", phone: "", role: "manager" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState("");

  async function invite(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setSent("");
    try {
      await api("company/members", { body: { ...form, phone: `+222${form.phone.replace(/\D/g, "")}` } });
      setSent(form.email);
      setForm({ full_name: "", email: "", phone: "", role: "manager" });
      reload();
    } catch (err) {
      setError(message(err, t("error")));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="members-title">
      <h3 className="card-title" id="members-title">{t("membersTitle")}</h3>
      {data && (
        <table className="mini">
          <tbody>
            {data.map((m) => (
              <tr key={m.id}>
                <td><strong>{m.full_name}</strong><span className="sub"><bdi dir="ltr">{m.email}</bdi></span></td>
                <td>{t(m.role === "admin" ? "roleAdmin" : "roleManager")}</td>
                <td>{m.active ? <span className="pill">{t("memberActive")}</span> : <span className="pill warn">{t("memberPending")}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {admin && (
        <form className="stack" onSubmit={invite} style={{ gap: 12 }}>
          <h4 style={{ margin: "8px 0 0" }}>{t("inviteTitle")}</h4>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="m-name">{t("fullName")}</label>
              <input id="m-name" className="input" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required />
            </div>
            <div className="field">
              <label htmlFor="m-email">{t("proEmail")}</label>
              <input id="m-email" className="input" type="email" dir="ltr" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
            </div>
            <div className="field">
              <label htmlFor="m-phone">{t("phoneLabel")}</label>
              <div className="row" style={{ gap: 8 }} dir="ltr">
                <span className="input" style={{ width: "auto", display: "flex", alignItems: "center", background: "var(--bg)", fontWeight: 700 }}>+222</span>
                <input id="m-phone" className="input" type="tel" inputMode="numeric" value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value.replace(/\D/g, "").slice(0, 8) })} required />
              </div>
            </div>
            <div className="field">
              <label htmlFor="m-role">{t("colRole")}</label>
              <select id="m-role" className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                <option value="manager">{t("roleManager")}</option>
                <option value="admin">{t("roleAdmin")}</option>
              </select>
            </div>
          </div>
          {error && <p className="error" role="alert">{error}</p>}
          {sent && <div className="banner green" role="status"><strong>{t("memberInvited", { email: sent })}</strong></div>}
          <button className="btn primary" disabled={busy || form.phone.length < 8} style={{ alignSelf: "flex-start" }}>
            {busy ? <span className="spinner sm" /> : t("inviteBtn")}
          </button>
        </form>
      )}
    </section>
  );
}
