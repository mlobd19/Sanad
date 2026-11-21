"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";

import { InsurerLogo } from "@/components/InsurerLogo";
import {
  api,
  ApiError,
  apiBlobUrl,
  downloadFile,
  getToken,
  setToken,
  type ClaimStatus,
  type InsurerClaim,
  type InsurerCommissions,
  type InsurerMe,
  type InsurerPolicy,
} from "@/lib/api";
import { date, money, month, num, percent } from "@/lib/format";
import { useI18n, type Key } from "@/lib/i18n";
import { useLoad } from "@/lib/useLoad";

type Tab = "pending" | "issued" | "claims" | "commissions";
type DecisionKind = "validate" | "refuse";
type Decision = { policy: InsurerPolicy; kind: DecisionKind };

const TABS: { id: Tab; label: Key }[] = [
  { id: "pending", label: "tabPending" },
  { id: "issued", label: "tabIssued" },
  { id: "claims", label: "tabClaims" },
  { id: "commissions", label: "tabCommissions" },
];

const KYC_PILL: Record<InsurerPolicy["kyc_status"], string> = {
  verified: "pill",
  pending: "pill warn",
  rejected: "pill bad",
  none: "pill quiet",
};

const STATUS_PILL: Record<string, string> = { active: "pill", refused: "pill bad", paid: "pill warn" };

const USAGE: Record<string, Key> = { personal: "usagePersonal", commercial: "usageCommercial", taxi: "usageTaxi" };

const PROVIDERS: Record<string, Key> = {
  simulated: "provider_simulated",
  bankily: "provider_bankily",
  masrvi: "provider_masrvi",
  sedad: "provider_sedad",
};

function intlPhone(phone: string) {
  return phone.replace(/^\+222(\d{2})(\d{2})(\d{2})(\d{2})$/, "+222 $1 $2 $3 $4");
}

// --- Page ---------------------------------------------------------------------------

export default function InsurerPortalPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [me, setMe] = useState<InsurerMe | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "notAgent" | "error">("loading");

  useEffect(() => {
    if (!getToken()) {
      router.replace("/assureur/connexion");
      return;
    }
    api<InsurerMe>("insurer/me")
      .then((data) => {
        setMe(data);
        setState("ready");
      })
      .catch((err) => setState(err instanceof ApiError && err.status === 403 ? "notAgent" : "error"));
  }, [router]);

  if (state === "ready" && me) return <Portal me={me} />;

  return (
    <div className="portal-login">
      <div className="box">
        <main className="sheet center" style={{ color: "var(--ink)", minHeight: 280 }}>
          {state === "loading" && <span className="spinner" aria-label={t("loading")} />}
          {state === "notAgent" && (
            <>
              <p className="error" role="alert">{t("portalNotAgent")}</p>
              <a className="btn primary" href="/assureur/connexion">{t("portalAgentLogin")}</a>
            </>
          )}
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

function Portal({ me }: { me: InsurerMe }) {
  const { t, lang, setLang } = useI18n();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("pending");
  const [decision, setDecision] = useState<Decision | null>(null);
  // Clé + variables (et non le texte traduit) : le message suit le changement de langue.
  const [toast, setToast] = useState<{ key: Key; vars: Record<string, string> } | null>(null);
  const pending = useLoad<InsurerPolicy[]>("insurer/policies?status=paid");
  const newClaims = useLoad<InsurerClaim[]>("insurer/claims?status=submitted");
  const [closing, setClosing] = useState<InsurerClaim | null>(null);
  const [claimsVersion, setClaimsVersion] = useState(0);
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({ pending: null, issued: null, claims: null, commissions: null });

  function logout() {
    setToken(null);
    router.replace("/assureur/connexion");
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

  function onDecided(policy: InsurerPolicy, kind: DecisionKind) {
    setDecision(null);
    setToast(
      kind === "validate"
        ? { key: "validatedToast", vars: { plate: policy.plate, number: policy.attestation?.number ?? "" } }
        : { key: "refusedToast", vars: { plate: policy.plate } },
    );
    pending.reload();
  }

  function onClaimUpdated(claim: InsurerClaim, key: Key) {
    setClosing(null);
    setToast({ key, vars: { number: claim.number } });
    newClaims.reload();
    setClaimsVersion((v) => v + 1);
  }

  const pendingCount = pending.data?.length ?? 0;
  const newClaimsCount = newClaims.data?.length ?? 0;
  const agentName = me.agent.full_name || intlPhone(me.agent.phone);

  return (
    <div className="portal">
      <header className="portal-head">
        <div className="portal-wrap">
          <InsurerLogo name={me.insurer.name} logo={me.insurer.logo} size={56} />
          <div className="grow">
            <h1>{me.insurer.name}</h1>
            <div className="sub">
              {me.insurer.legal_name} · {t("portalName")} {t("appName")}
            </div>
          </div>
          <div className="agent">
            <strong><bdi>{agentName}</bdi></strong>
            {me.agent.full_name && <bdi dir="ltr">{intlPhone(me.agent.phone)}</bdi>}
          </div>
          <button type="button" className="btn-on-dark" onClick={() => setLang(lang === "fr" ? "ar" : "fr")}>
            {lang === "fr" ? "العربية" : "Français"}
          </button>
          <button type="button" className="btn-on-dark" onClick={logout}>{t("logout")}</button>
        </div>
      </header>

      <nav className="portal-tabs">
        <div className="portal-wrap" role="tablist" aria-label={t("portalSections")}>
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
              {id === "pending" && pendingCount > 0 && <span className="count">{num(pendingCount, lang)}</span>}
              {id === "claims" && newClaimsCount > 0 && <span className="count">{num(newClaimsCount, lang)}</span>}
            </button>
          ))}
        </div>
      </nav>

      <main className="portal-wrap portal-main" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {toast && (
          <div className="banner green" role="status">
            <span className="grow" style={{ fontWeight: 600 }}>{t(toast.key, toast.vars)}</span>
            <button type="button" className="btn link" onClick={() => setToast(null)}>{t("close")}</button>
          </div>
        )}
        {tab === "pending" && (
          <PendingTab
            policies={pending.data}
            error={pending.error}
            reload={pending.reload}
            onDecide={(policy, kind) => setDecision({ policy, kind })}
          />
        )}
        {tab === "issued" && <IssuedTab />}
        {tab === "claims" && (
          <ClaimsTab key={claimsVersion} onTaken={(c) => onClaimUpdated(c, "takenToast")} onClose={setClosing} />
        )}
        {tab === "commissions" && <CommissionsTab />}
      </main>

      {decision && <DecisionDialog decision={decision} onClose={() => setDecision(null)} onDone={onDecided} />}
      {closing && (
        <CloseClaimDialog claim={closing} onClose={() => setClosing(null)} onDone={(c) => onClaimUpdated(c, "closedToast")} />
      )}
    </div>
  );
}

// --- Éléments communs ------------------------------------------------------------------

function SectionHead({ title, reload, children }: { title: string; reload: () => void; children?: ReactNode }) {
  const { t } = useI18n();
  return (
    <div className="between" style={{ flexWrap: "wrap" }}>
      <h2>{title}</h2>
      <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
        {children}
        <button type="button" className="btn outline" onClick={reload}>{t("refresh")}</button>
      </div>
    </div>
  );
}

function Loadable<T>({ data, error, reload, empty, children }: {
  data: T[] | null;
  error: string;
  reload: () => void;
  empty: string;
  children: (rows: T[]) => ReactNode;
}) {
  const { t } = useI18n();
  if (error) {
    return (
      <div className="banner red" role="alert">
        <span className="grow">{error === "error" ? t("error") : error}</span>
        <button type="button" className="btn link" onClick={reload}>{t("retry")}</button>
      </div>
    );
  }
  if (!data) return <div className="center" style={{ minHeight: 200 }}><span className="spinner" aria-label={t("loading")} /></div>;
  if (!data.length) return <div className="card"><p className="ink2" style={{ margin: 0 }}>{empty}</p></div>;
  return <div className="ptable-wrap">{children(data)}</div>;
}

function Premium({ amount, indicative }: { amount: number; indicative: boolean }) {
  const { t, lang } = useI18n();
  return (
    <>
      <strong className="num">{money(amount, lang)}</strong>
      {indicative && <span className="badge-sand" style={{ display: "inline-block", marginTop: 4 }}>{t("indicative")}</span>}
    </>
  );
}

function CustomerCell({ p }: { p: InsurerPolicy }) {
  const { t } = useI18n();
  return (
    <td data-label={t("colCustomer")}>
      {p.company && (
        <>
          <strong>{p.company.legal_name}</strong>
          <span className="sub"><bdi dir="ltr">{t("nifShort", { nif: p.company.nif })}</bdi></span>
          <span className="sub">{t("subscribedBy", { name: p.customer.full_name || p.customer.phone })}</span>
        </>
      )}
      {!p.company && <strong>{p.customer.full_name || <span className="muted">{t("noName")}</span>}</strong>}
      <span className="sub"><bdi dir="ltr">{intlPhone(p.customer.phone)}</bdi></span>
      {p.customer.nni && <span className="sub">{t("nniShort", { nni: p.customer.nni })}</span>}
    </td>
  );
}

function VehicleCell({ p }: { p: InsurerPolicy }) {
  const { t, lang } = useI18n();
  const details = [
    p.vehicle.make,
    p.vehicle.fiscal_power ? t("cvShort", { n: num(p.vehicle.fiscal_power, lang) }) : "",
    USAGE[p.vehicle.usage] ? t(USAGE[p.vehicle.usage]) : p.vehicle.usage,
  ].filter(Boolean);
  return (
    <td data-label={t("vehicle")}>
      <bdi className="plate" dir="ltr">{p.plate}</bdi>
      {details.length > 0 && (
        <span className="sub">
          {details.map((d, i) => (
            <span key={i}>{i > 0 && " · "}<bdi>{d}</bdi></span>
          ))}
        </span>
      )}
    </td>
  );
}

// --- Onglet « Demandes à valider » -----------------------------------------------------

function PendingTab({ policies, error, reload, onDecide }: {
  policies: InsurerPolicy[] | null;
  error: string;
  reload: () => void;
  onDecide: (policy: InsurerPolicy, kind: DecisionKind) => void;
}) {
  const { t, lang } = useI18n();
  return (
    <>
      <SectionHead title={t("tabPending")} reload={reload} />
      <p className="note" style={{ margin: 0 }}>{t("indicativeNote")}</p>
      <Loadable data={policies} error={error} reload={reload} empty={t("noPending")}>
        {(rows) => (
          <table className="ptable">
            <thead>
              <tr>
                <th scope="col">{t("colCustomer")}</th>
                <th scope="col">{t("vehicle")}</th>
                <th scope="col">{t("formula")}</th>
                <th scope="col">{t("colPremium")}</th>
                <th scope="col">{t("colPayment")}</th>
                <th scope="col">{t("colKyc")}</th>
                <th scope="col">{t("colReceived")}</th>
                <th scope="col"><span className="sr-only">{t("colActions")}</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id}>
                  <CustomerCell p={p} />
                  <VehicleCell p={p} />
                  <td data-label={t("formula")}><strong>{p.product}</strong></td>
                  <td data-label={t("colPremium")}><Premium amount={p.premium} indicative={p.indicative} /></td>
                  <td data-label={t("colPayment")}>
                    {p.payment_provider ? (PROVIDERS[p.payment_provider] ? t(PROVIDERS[p.payment_provider]) : p.payment_provider) : "—"}
                  </td>
                  <td data-label={t("colKyc")}><span className={KYC_PILL[p.kyc_status]}>{t(`kyc_${p.kyc_status}`)}</span></td>
                  <td data-label={t("colReceived")} className="num">{date(p.created_at, lang)}</td>
                  <td className="act wide">
                    <div className="actions">
                      <button
                        type="button"
                        className="btn primary"
                        onClick={() => onDecide(p, "validate")}
                        aria-label={`${t("validate")} · ${p.plate}`}
                      >
                        {t("validate")}
                      </button>
                      <button
                        type="button"
                        className="btn danger"
                        onClick={() => onDecide(p, "refuse")}
                        aria-label={`${t("refuse")} · ${p.plate}`}
                      >
                        {t("refuse")}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Loadable>
    </>
  );
}

// --- Onglet « Polices émises » (et refusées) -----------------------------------------------

function IssuedTab() {
  const { t, lang } = useI18n();
  const [filter, setFilter] = useState<"issued" | "refused">("issued");
  const { data, error, reload } = useLoad<InsurerPolicy[]>(
    `insurer/policies?status=${filter === "issued" ? "active,expired,cancelled" : "refused"}`,
  );

  return (
    <>
      <SectionHead title={t("tabIssued")} reload={reload}>
        <div className="chips" role="group" aria-label={t("filterPolicies")}>
          <button type="button" aria-pressed={filter === "issued"} onClick={() => setFilter("issued")}>{t("filterIssued")}</button>
          <button type="button" aria-pressed={filter === "refused"} onClick={() => setFilter("refused")}>{t("filterRefused")}</button>
        </div>
      </SectionHead>
      <Loadable data={data} error={error} reload={reload} empty={t(filter === "issued" ? "noIssued" : "noRefused")}>
        {(rows) =>
          filter === "issued" ? (
            <table className="ptable">
              <thead>
                <tr>
                  <th scope="col">{t("colCustomer")}</th>
                  <th scope="col">{t("vehicle")}</th>
                  <th scope="col">{t("formula")}</th>
                  <th scope="col">{t("colPremium")}</th>
                  <th scope="col">{t("colStatus")}</th>
                  <th scope="col">{t("period")}</th>
                  <th scope="col">{t("colAttestation")}</th>
                  <th scope="col">{t("colInsurerRef")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id}>
                    <CustomerCell p={p} />
                    <VehicleCell p={p} />
                    <td data-label={t("formula")}><strong>{p.product}</strong></td>
                    <td data-label={t("colPremium")}><Premium amount={p.premium} indicative={p.indicative} /></td>
                    <td data-label={t("colStatus")}>
                      <span className={STATUS_PILL[p.status] ?? "pill quiet"}>{t(`status_${p.status}`)}</span>
                    </td>
                    <td data-label={t("period")} className="num">
                      {date(p.starts_on, lang)}
                      <span className="sub">{t("validTo")} {date(p.ends_on, lang)}</span>
                    </td>
                    <td data-label={t("colAttestation")} className="num">
                      <bdi dir="ltr">{p.attestation?.number ?? "—"}</bdi>
                      {p.attestation && p.status === "active" && <PdfButton id={p.attestation.id} number={p.attestation.number} />}
                    </td>
                    <td data-label={t("colInsurerRef")} className="num"><bdi dir="ltr">{p.insurer_reference || "—"}</bdi></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table className="ptable">
              <thead>
                <tr>
                  <th scope="col">{t("colCustomer")}</th>
                  <th scope="col">{t("vehicle")}</th>
                  <th scope="col">{t("formula")}</th>
                  <th scope="col">{t("colPremium")}</th>
                  <th scope="col">{t("colRefusedOn")}</th>
                  <th scope="col">{t("colReason")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id}>
                    <CustomerCell p={p} />
                    <VehicleCell p={p} />
                    <td data-label={t("formula")}><strong>{p.product}</strong></td>
                    <td data-label={t("colPremium")}><Premium amount={p.premium} indicative={p.indicative} /></td>
                    <td data-label={t("colRefusedOn")} className="num">{p.decided_at ? date(p.decided_at, lang) : "—"}</td>
                    <td data-label={t("colReason")} className="wide reason">{p.refusal_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        }
      </Loadable>
    </>
  );
}

function PdfButton({ id, number }: { id: number; number: string }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function download() {
    setBusy(true);
    setError("");
    try {
      await downloadFile(`attestations/${id}/pdf`, `attestation-${number}.pdf`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("error"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button
        type="button"
        className="btn outline"
        style={{ display: "flex", minHeight: 36, padding: "0 12px", fontSize: 13, marginTop: 6 }}
        onClick={download}
        disabled={busy}
        aria-label={t("pdfOf", { number })}
      >
        {busy ? <span className="spinner sm" /> : t("pdf")}
      </button>
      {error && <span className="error small" role="alert" style={{ display: "block" }}>{error}</span>}
    </>
  );
}

// --- Onglet « Commissions » --------------------------------------------------------------

function CommissionsTab() {
  const { t, lang } = useI18n();
  const { data, error, reload } = useLoad<InsurerCommissions>("insurer/commissions");
  const badge = data?.indicative ? <span className="badge-sand">{t("indicative")}</span> : null;

  return (
    <>
      <SectionHead title={t("tabCommissions")} reload={reload} />
      {data?.indicative && (
        <div className="banner sand">
          <span className="badge-sand">{t("indicative")}</span>
          <span>{t("commissionNote")}</span>
        </div>
      )}
      {data && data.months.length > 0 && (
        <div className="month-cards">
          {data.months.map((m) => (
            <section key={m.period} className="card" aria-label={month(m.period, lang)}>
              <div className="between">
                <strong style={{ textTransform: "capitalize" }}>{month(m.period, lang)}</strong>
                {badge}
              </div>
              <span className="big num">{money(m.amount, lang)}</span>
              <span className="ink2 small">
                {t("policiesCount", { count: num(m.policies, lang) })} · {t("premiumsTotal", { amount: money(m.premiums, lang) })}
              </span>
              <span className="small" style={{ fontWeight: 600 }}>
                {t("paidAmount", { amount: money(m.paid, lang) })} · {t("dueAmount", { amount: money(m.due, lang) })}
              </span>
            </section>
          ))}
        </div>
      )}
      {data && data.items.length > 0 && <h2 style={{ fontSize: 18 }}>{t("commissionDetail")}</h2>}
      <Loadable data={data?.items ?? null} error={error} reload={reload} empty={t("noCommissions")}>
        {(rows) => (
          <table className="ptable">
            <thead>
              <tr>
                <th scope="col">{t("colPolicy")}</th>
                <th scope="col">{t("formula")}</th>
                <th scope="col">{t("colPremium")}</th>
                <th scope="col">{t("colRate")}</th>
                <th scope="col">{t("colCommission")}</th>
                <th scope="col">{t("colMonth")}</th>
                <th scope="col">{t("colStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id}>
                  <td data-label={t("colPolicy")}>
                    <bdi className="plate" dir="ltr">{c.plate}</bdi>
                    <span className="sub">{t("policyNo", { id: num(c.policy_id, lang) })}</span>
                  </td>
                  <td data-label={t("formula")}>{c.product}</td>
                  <td data-label={t("colPremium")} className="num">{money(c.premium, lang)}</td>
                  <td data-label={t("colRate")} className="num">{percent(c.rate, lang)}</td>
                  <td data-label={t("colCommission")}>
                    <Premium amount={c.amount} indicative={Boolean(data?.indicative)} />
                  </td>
                  <td data-label={t("colMonth")} style={{ textTransform: "capitalize" }}>{month(c.period, lang)}</td>
                  <td data-label={t("colStatus")}>
                    <span className={c.is_paid ? "pill" : "pill warn"}>{t(c.is_paid ? "commissionPaid" : "commissionDue")}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Loadable>
    </>
  );
}

// --- Fenêtre de décision -------------------------------------------------------------------

function DecisionDialog({ decision, onClose, onDone }: {
  decision: Decision;
  onClose: () => void;
  onDone: (policy: InsurerPolicy, kind: DecisionKind) => void;
}) {
  const { t, lang } = useI18n();
  const { policy, kind } = decision;
  const ref = useRef<HTMLDialogElement>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const validate = kind === "validate";

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!validate && !text.trim()) {
      setError(t("reasonRequired"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      const body = validate ? { insurer_reference: text.trim() } : { reason: text.trim() };
      const updated = await api<InsurerPolicy>(`insurer/policies/${policy.id}/${kind}`, { body });
      onDone(updated, kind);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("error"));
      setBusy(false);
    }
  }

  return (
    <dialog ref={ref} className="pdialog" aria-labelledby="decision-title" onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <h2 id="decision-title">
          {t(validate ? "validateTitle" : "refuseTitle")} <bdi dir="ltr">{policy.plate}</bdi>
        </h2>
        <p className="ink2" style={{ margin: 0 }}>{t(validate ? "validateText" : "refuseText")}</p>
        <div className="card" style={{ background: "var(--bg)", border: "none", gap: 4 }}>
          <strong>{policy.customer.full_name || t("noName")}</strong>
          <span className="ink2 small">
            {policy.product} · {money(policy.premium, lang)}
            {policy.indicative && ` (${t("indicative")})`}
          </span>
        </div>
        <div className="field">
          <label htmlFor="decision-input">{t(validate ? "insurerRefLabel" : "reasonLabel")}</label>
          {validate ? (
            <input
              id="decision-input"
              className="input"
              value={text}
              onChange={(e) => setText(e.target.value)}
              maxLength={60}
              autoComplete="off"
              autoFocus
            />
          ) : (
            <textarea
              id="decision-input"
              className="input"
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                if (e.target.value.trim()) setError("");
              }}
              maxLength={255}
              required
              aria-required="true"
              aria-invalid={Boolean(error)}
              aria-describedby={error ? "decision-error" : undefined}
              autoFocus
            />
          )}
        </div>
        {error && <p className="error" id="decision-error" role="alert">{error}</p>}
        <div className="row" style={{ justifyContent: "flex-end", flexWrap: "wrap" }}>
          <button type="button" className="btn outline" onClick={() => ref.current?.close()} disabled={busy}>
            {t("cancel")}
          </button>
          <button className={`btn ${validate ? "primary" : "danger-solid"}`} disabled={busy}>
            {busy ? <span className="spinner sm" style={{ borderTopColor: "#fff" }} /> : t(validate ? "confirmValidate" : "confirmRefuse")}
          </button>
        </div>
      </form>
    </dialog>
  );
}

// --- Onglet « Sinistres » -------------------------------------------------------------------

const CLAIM_FILTERS: { id: ClaimStatus; label: Key }[] = [
  { id: "submitted", label: "filterNewClaims" },
  { id: "in_review", label: "filterInReview" },
  { id: "closed", label: "filterClosed" },
];

function ClaimsTab({ onTaken, onClose }: { onTaken: (claim: InsurerClaim) => void; onClose: (claim: InsurerClaim) => void }) {
  const { t, lang } = useI18n();
  const [filter, setFilter] = useState<ClaimStatus>("submitted");
  const { data, error, reload } = useLoad<InsurerClaim[]>(`insurer/claims?status=${filter}`);
  const [busy, setBusy] = useState<number | null>(null);
  const [actionError, setActionError] = useState("");

  async function take(claim: InsurerClaim) {
    setBusy(claim.id);
    setActionError("");
    try {
      onTaken(await api<InsurerClaim>(`insurer/claims/${claim.id}/take`, { method: "POST" }));
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : t("error"));
    } finally {
      setBusy(null);
    }
  }

  async function openPhoto(claim: InsurerClaim, photoId: number) {
    // Fenêtre ouverte tout de suite (sinon bloquée), puis remplie avec la photo chargée avec le jeton.
    const win = window.open("", "_blank");
    try {
      const url = await apiBlobUrl(`insurer/claims/${claim.id}/photos/${photoId}`);
      if (win) win.location.href = url;
    } catch {
      win?.close();
      setActionError(t("error"));
    }
  }

  return (
    <>
      <SectionHead title={t("tabClaims")} reload={reload}>
        <div className="chips" role="group" aria-label={t("tabClaims")}>
          {CLAIM_FILTERS.map((f) => (
            <button key={f.id} type="button" aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>{t(f.label)}</button>
          ))}
        </div>
      </SectionHead>
      {actionError && <div className="banner red" role="alert">{actionError}</div>}
      <Loadable data={data} error={error} reload={reload} empty={t(`noClaims_${filter}` as Key)}>
        {(rows) => (
          <table className="ptable">
            <thead>
              <tr>
                <th scope="col">{t("colClaim")}</th>
                <th scope="col">{t("colCustomer")}</th>
                <th scope="col">{t("vehicle")}</th>
                <th scope="col">{t("colOccurred")}</th>
                <th scope="col">{t("colCircumstances")}</th>
                <th scope="col">{t("claimPhotos")}</th>
                <th scope="col">{filter === "closed" ? t("claimInsurerNote") : <span className="sr-only">{t("colActions")}</span>}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id}>
                  <td data-label={t("colClaim")}>
                    <strong><bdi dir="ltr">{c.number}</bdi></strong>
                    <span className="sub">{t(`claimKind_${c.kind}` as Key)} · {t("colReceived")} {date(c.created_at, lang)}</span>
                  </td>
                  <td data-label={t("colCustomer")}>
                    {c.customer.company ? (
                      <>
                        <strong><bdi>{c.customer.company}</bdi></strong>
                        <span className="sub">{t("declaredBy", { name: c.customer.full_name || c.customer.phone })}</span>
                      </>
                    ) : (
                      <strong>{c.customer.full_name || <span className="muted">{t("noName")}</span>}</strong>
                    )}
                    <span className="sub"><bdi dir="ltr">{intlPhone(c.customer.phone)}</bdi></span>
                  </td>
                  <td data-label={t("vehicle")}>
                    <bdi className="plate" dir="ltr">{c.policy.plate}</bdi>
                    <span className="sub">{[c.policy.make, c.policy.product].filter(Boolean).join(" · ")}</span>
                  </td>
                  <td data-label={t("colOccurred")} className="num">
                    {date(c.occurred_on, lang)}
                    <span className="sub">{c.place}</span>
                  </td>
                  <td data-label={t("colCircumstances")} style={{ maxWidth: 320 }}>
                    {c.injuries && <span className="pill bad" style={{ marginBottom: 4 }}>{t("injuriesFlag")}</span>}
                    <span style={{ whiteSpace: "pre-line" }}>{c.description}</span>
                    {c.third_party_plate && (
                      <span className="sub"><bdi dir="ltr">{t("thirdPartyShort", { plate: c.third_party_plate })}</bdi></span>
                    )}
                  </td>
                  <td data-label={t("claimPhotos")}>
                    {c.photo_ids.length === 0 && <span className="muted">{t("noPhotos")}</span>}
                    <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                      {c.photo_ids.map((pid, i) => (
                        <button key={pid} type="button" className="btn link" onClick={() => openPhoto(c, pid)}
                          aria-label={`${t("photoN", { n: num(i + 1, lang) })} · ${c.number}`}>
                          {t("photoN", { n: num(i + 1, lang) })}
                        </button>
                      ))}
                    </div>
                  </td>
                  {c.status === "closed" ? (
                    <td data-label={t("claimInsurerNote")}>
                      {c.closing_note}
                      {c.handled_by && <span className="sub">{t("handledBy", { name: c.handled_by })}</span>}
                    </td>
                  ) : (
                    <td className="act wide">
                      <div className="actions">
                        {c.status === "submitted" && (
                          <button type="button" className="btn primary" disabled={busy === c.id} onClick={() => take(c)}
                            aria-label={`${t("takeClaim")} · ${c.number}`}>
                            {t("takeClaim")}
                          </button>
                        )}
                        <button type="button" className="btn outline" onClick={() => onClose(c)}
                          aria-label={`${t("closeClaim")} · ${c.number}`}>
                          {t("closeClaim")}
                        </button>
                      </div>
                      {c.handled_by && <span className="sub">{t("handledBy", { name: c.handled_by })}</span>}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Loadable>
    </>
  );
}

function CloseClaimDialog({ claim, onClose, onDone }: {
  claim: InsurerClaim;
  onClose: () => void;
  onDone: (claim: InsurerClaim) => void;
}) {
  const { t } = useI18n();
  const ref = useRef<HTMLDialogElement>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!note.trim()) {
      setError(t("noteRequired"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      onDone(await api<InsurerClaim>(`insurer/claims/${claim.id}/close`, { body: { note: note.trim() } }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("error"));
      setBusy(false);
    }
  }

  return (
    <dialog ref={ref} className="pdialog" aria-labelledby="close-claim-title" onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <h2 id="close-claim-title">{t("closeClaimTitle")} <bdi dir="ltr">{claim.number}</bdi></h2>
        <p className="ink2" style={{ margin: 0 }}>{t("closeClaimText")}</p>
        <div className="card" style={{ background: "var(--bg)", border: "none", gap: 4 }}>
          <strong><bdi>{claim.customer.company || claim.customer.full_name || t("noName")}</bdi></strong>
          <span className="ink2 small"><bdi dir="ltr">{claim.policy.plate}</bdi> · {t(`claimKind_${claim.kind}` as Key)}</span>
        </div>
        <div className="field">
          <label htmlFor="close-note">{t("closeNoteLabel")}</label>
          <textarea id="close-note" className="input" value={note} maxLength={500} required aria-required="true"
            aria-invalid={Boolean(error)} aria-describedby={error ? "close-error" : undefined} autoFocus
            onChange={(e) => {
              setNote(e.target.value);
              if (e.target.value.trim()) setError("");
            }} />
        </div>
        {error && <p className="error" id="close-error" role="alert">{error}</p>}
        <div className="row" style={{ justifyContent: "flex-end", flexWrap: "wrap" }}>
          <button type="button" className="btn outline" onClick={() => ref.current?.close()} disabled={busy}>{t("cancel")}</button>
          <button className="btn primary" disabled={busy}>
            {busy ? <span className="spinner sm" style={{ borderTopColor: "#fff" }} /> : t("confirmClose")}
          </button>
        </div>
      </form>
    </dialog>
  );
}
