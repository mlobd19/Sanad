"use client";

import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";

import { Icon } from "@/components/Icon";
import { InsurerLogo } from "@/components/InsurerLogo";
import { ErrorLine } from "@/components/Shell";
import { api, ApiError, type Quote, type TravelerCheck, type TravelLimits, type Trip, type User } from "@/lib/api";
import { countryName, destinationsLabel, searchCountries } from "@/lib/countries";
import { date, money } from "@/lib/format";
import { useI18n, type Key } from "@/lib/i18n";

// Assurance voyage « Monde entier » : composants partagés par l'app client (/voyage) et l'onglet
// « Missions » de l'espace entreprise. `base` : "" (particulier) ou "company/" (entreprise).

const ERROR_CODES = [
  "invalid_destination", "missing_destination", "too_many_destinations", "invalid_departure", "invalid_return",
  "departure_past", "return_before_departure", "too_long", "locked", "too_many_travelers", "already_added",
  "invalid_passport", "invalid_birth_date", "name_required", "not_found", "unavailable", "invalid_nni",
  "traveler_overlap", "no_travelers", "quote_outdated",
];

/** Message d'erreur traduit (code renvoyé par l'API), sinon le message du serveur. */
export function useTravelError() {
  const { t } = useI18n();
  return (err: unknown) => {
    if (err instanceof ApiError && ERROR_CODES.includes(err.code)) return t(`travelErr_${err.code}` as Key);
    return err instanceof ApiError ? err.message : t("error");
  };
}

const today = () => new Date().toISOString().slice(0, 10);

function addDaysIso(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Durée affichée, départ et retour compris (comme le backend). */
export function tripDays(departure: string, back: string): number {
  return Math.round((Date.parse(back) - Date.parse(departure)) / 86_400_000) + 1;
}

/** « Espagne, France · 12 déc. → 26 déc. · 15 jours » */
export function TripSummary({ trip, travelers }: { trip: Pick<Trip, "destinations" | "departure_on" | "return_on" | "days">; travelers?: number }) {
  const { t, lang } = useI18n();
  return (
    <span>
      {destinationsLabel(trip.destinations, lang, 3)} · {date(trip.departure_on, lang)} → {date(trip.return_on, lang)} ·{" "}
      {t("tripDays", { count: trip.days })}
      {travelers !== undefined && <> · {t("travelersCount", { count: travelers })}</>}
    </span>
  );
}

// --- Destinations et dates -----------------------------------------------------------------------

export function TripForm({ base, initial, onCreated, submitLabel }: {
  base: "" | "company/";
  initial?: Pick<Trip, "destinations" | "departure_on" | "return_on"> | null;
  onCreated: (trip: Trip) => void;
  submitLabel?: string;
}) {
  const { t, lang } = useI18n();
  const travelError = useTravelError();
  const ids = useId();
  const [destinations, setDestinations] = useState<string[]>(initial?.destinations ?? []);
  const [query, setQuery] = useState("");
  const [departure, setDeparture] = useState(initial?.departure_on ?? addDaysIso(today(), 7));
  const [back, setBack] = useState(initial?.return_on ?? addDaysIso(today(), 20));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const search = useRef<HTMLInputElement>(null);
  const matches = searchCountries(query, lang).filter((c) => !destinations.includes(c.code));
  const days = departure && back ? tripDays(departure, back) : 0;

  function pick(code: string) {
    setDestinations((list) => (list.includes(code) ? list : [...list, code].slice(0, 10)));
    setQuery("");
    search.current?.focus();
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!destinations.length) return setError(t("travelErr_missing_destination"));
    setBusy(true);
    setError("");
    try {
      onCreated(await api<Trip>(`${base}trips`, { body: { destinations, departure_on: departure, return_on: back } }));
    } catch (err) {
      setError(travelError(err));
      setBusy(false);
    }
  }

  return (
    <form className="stack" style={{ gap: 18 }} onSubmit={submit} noValidate>
      <div className="field">
        <label htmlFor={`${ids}-q`}>{t("destinations")}</label>
        {destinations.length > 0 && (
          <ul className="chips" style={{ flexWrap: "wrap", listStyle: "none", padding: 0, margin: "0 0 4px" }}>
            {destinations.map((code) => (
              <li key={code}>
                <button type="button" aria-pressed="true" onClick={() => setDestinations((l) => l.filter((c) => c !== code))}
                  aria-label={t("removeDestination", { country: countryName(code, lang) })}>
                  {countryName(code, lang)}
                  <Icon name="close" size={16} strokeWidth={2.4} />
                </button>
              </li>
            ))}
          </ul>
        )}
        <input id={`${ids}-q`} ref={search} className="input" value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder={t("destinationSearch")} autoComplete="off" spellCheck={false} aria-describedby={`${ids}-hint`}
          onKeyDown={(e) => {
            if (e.key === "Enter" && matches[0]) {
              e.preventDefault();
              pick(matches[0].code);
            }
          }} />
        {query.trim() && (
          <ul className="country-results" role="listbox" aria-label={t("destinations")}>
            {matches.length === 0 && <li className="muted">{t("noCountry")}</li>}
            {matches.map((c) => (
              <li key={c.code} role="option" aria-selected="false">
                <button type="button" onClick={() => pick(c.code)}>{c[lang]}</button>
              </li>
            ))}
          </ul>
        )}
        <span id={`${ids}-hint`} className="small muted">{t("destinationHint")}</span>
      </div>

      <div className="grid2">
        <div className="field">
          <label htmlFor={`${ids}-dep`}>{t("departureOn")}</label>
          <input id={`${ids}-dep`} className="input" type="date" value={departure} min={today()} required
            onChange={(e) => {
              setDeparture(e.target.value);
              if (back < e.target.value) setBack(e.target.value);
            }} />
        </div>
        <div className="field">
          <label htmlFor={`${ids}-ret`}>{t("returnOn")}</label>
          <input id={`${ids}-ret`} className="input" type="date" value={back} min={departure} max={addDaysIso(departure, 91)}
            required onChange={(e) => setBack(e.target.value)} />
        </div>
      </div>
      <p className="small ink2" style={{ margin: 0 }}>{days > 0 ? t("tripDays", { count: days }) : " "}</p>
      <ErrorLine message={error} />
      <button className="btn primary block tall" disabled={busy}>
        {busy && <span className="spinner sm" aria-hidden="true" />}
        {submitLabel ?? t("continue")}
      </button>
    </form>
  );
}

// --- Voyageurs ------------------------------------------------------------------------------------

export function VerificationPill({ verification }: { verification: "verified" | "declared" }) {
  const { t } = useI18n();
  return verification === "verified"
    ? <span className="pill">{t("verifiedName")}</span>
    : <span className="pill warn">{t("declaredName")}</span>;
}

/** Voyageurs d'un voyage : liste, retrait, ajout (NNI vérifié auprès de l'ANRPTS, passeport, naissance). */
export function TravelersEditor({ base, trip, onChange, me, max }: {
  base: "" | "company/";
  trip: Trip;
  onChange: (trip: Trip) => void;
  /** Particulier : bouton « M'ajouter » pré-rempli avec le NNI du profil. */
  me?: User | null;
  max: number;
}) {
  const { t, lang } = useI18n();
  const travelError = useTravelError();
  const [adding, setAdding] = useState(trip.travelers.length === 0);
  const [prefill, setPrefill] = useState("");
  const [error, setError] = useState("");
  const myNni = me?.nni && !trip.travelers.some((x) => x.nni === me.nni) ? me.nni : "";

  async function remove(id: number) {
    setError("");
    try {
      onChange(await api<Trip>(`${base}trips/${trip.id}/travelers/${id}`, { method: "DELETE" }));
    } catch (err) {
      setError(travelError(err));
    }
  }

  return (
    <div className="stack" style={{ gap: 12 }}>
      {trip.travelers.length > 0 && (
        <ul className="stack" style={{ gap: 10, listStyle: "none", padding: 0, margin: 0 }} aria-label={t("travelersTitle")}>
          {trip.travelers.map((x) => (
            <li key={x.id} className="card" style={{ gap: 6 }}>
              <div className="between" style={{ alignItems: "flex-start" }}>
                <div className="stack" style={{ gap: 2, minWidth: 0 }}>
                  <strong>{lang === "ar" && x.full_name_ar ? x.full_name_ar : x.full_name}</strong>
                  <span className="small ink2">
                    <bdi dir="ltr">{t("passportShort", { passport: x.passport_number })}</bdi> · {t("bornOn", { date: date(x.birth_date, lang) })}
                  </span>
                </div>
                {!trip.locked && (
                  <button type="button" className="iconbtn" onClick={() => remove(x.id)}
                    aria-label={t("removeTraveler", { name: x.full_name })}>
                    <Icon name="close" size={20} strokeWidth={2.2} />
                  </button>
                )}
              </div>
              <span><VerificationPill verification={x.verification} /></span>
            </li>
          ))}
        </ul>
      )}
      <ErrorLine message={error} />
      {!trip.locked && trip.travelers.length < max && (adding ? (
        <AddTravelerForm key={prefill} base={base} trip={trip} initialNni={prefill}
          onAdded={(next) => { onChange(next); setAdding(false); setPrefill(""); }}
          onCancel={trip.travelers.length ? () => setAdding(false) : undefined} />
      ) : (
        <div className="grid2" style={myNni ? undefined : { gridTemplateColumns: "1fr" }}>
          {myNni && (
            <button type="button" className="btn outline" onClick={() => { setPrefill(myNni); setAdding(true); }}>
              <Icon name="user" size={18} strokeWidth={2} />
              {t("addMe")}
            </button>
          )}
          <button type="button" className="btn outline" onClick={() => { setPrefill(""); setAdding(true); }}>
            <Icon name="plus" size={18} strokeWidth={2} />
            {t("addTraveler")}
          </button>
        </div>
      ))}
    </div>
  );
}

function AddTravelerForm({ base, trip, initialNni, onAdded, onCancel }: {
  base: "" | "company/";
  trip: Trip;
  initialNni: string;
  onAdded: (trip: Trip) => void;
  onCancel?: () => void;
}) {
  const { t, lang } = useI18n();
  const travelError = useTravelError();
  const ids = useId();
  const [nni, setNni] = useState(initialNni);
  const [check, setCheck] = useState<TravelerCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [passport, setPassport] = useState("");
  const [birth, setBirth] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Dès les 10 chiffres saisis : nom officiel (eID) ou, sans eID, champ « nom du passeport ».
  useEffect(() => {
    setCheck(null);
    if (!/^\d{10}$/.test(nni)) return;
    let alive = true;
    setChecking(true);
    setError("");
    api<TravelerCheck>(`${base}travelers/check`, { body: { nni } })
      .then((result) => alive && setCheck(result))
      .catch((err) => alive && setError(travelError(err)))
      .finally(() => alive && setChecking(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nni, base]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onAdded(await api<Trip>(`${base}trips/${trip.id}/travelers`, {
        body: { nni, passport_number: passport, birth_date: birth, full_name: name },
      }));
    } catch (err) {
      setError(travelError(err));
      setBusy(false);
    }
  }

  const officialName = check?.status === "verified" ? (lang === "ar" && check.full_name_ar ? check.full_name_ar : check.full_name) : "";

  return (
    <form className="card stack" style={{ gap: 14 }} onSubmit={submit} noValidate aria-label={t("addTraveler")}>
      <div className="field">
        <label htmlFor={`${ids}-nni`}>{t("travelerNni")}</label>
        <input id={`${ids}-nni`} className="input" dir="ltr" inputMode="numeric" maxLength={10} minLength={10} required
          value={nni} onChange={(e) => setNni(e.target.value.replace(/\D/g, "").slice(0, 10))} autoComplete="off" />
        {/* Place réservée : nom officiel, vérification en cours ou rien. */}
        <span className="small" style={{ minHeight: "1.45em" }} aria-live="polite">
          {checking ? <span className="muted">{t("checkNni")}…</span>
            : officialName ? <><strong>{officialName}</strong> <span className="pill" style={{ marginInlineStart: 6 }}>{t("verifiedName")}</span></>
              : " "}
        </span>
      </div>
      {check?.status === "declared" && (
        <div className="field">
          <label htmlFor={`${ids}-name`}>{t("passportName")}</label>
          <input id={`${ids}-name`} className="input" dir="ltr" value={name} maxLength={120} required autoComplete="off"
            autoCapitalize="characters" onChange={(e) => setName(e.target.value)} aria-describedby={`${ids}-no-eid`} />
          <span id={`${ids}-no-eid`} className="small muted">{t("noEidNote")}</span>
        </div>
      )}
      <div className="field">
        <label htmlFor={`${ids}-pp`}>{t("passportNumber")}</label>
        <input id={`${ids}-pp`} className="input" dir="ltr" value={passport} maxLength={15} minLength={6} required autoComplete="off"
          autoCapitalize="characters" spellCheck={false} onChange={(e) => setPassport(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ""))} />
      </div>
      <div className="field">
        <label htmlFor={`${ids}-birth`}>{t("birthDate")}</label>
        <input id={`${ids}-birth`} className="input" type="date" value={birth} max={today()} required autoComplete="off"
          onChange={(e) => setBirth(e.target.value)} />
      </div>
      <ErrorLine message={error} />
      <div className="stack" style={{ gap: 8 }}>
        <button className="btn primary block" disabled={busy || checking || !check}>
          {busy && <span className="spinner sm" aria-hidden="true" />}
          {t("addTraveler")}
        </button>
        {onCancel && <button type="button" className="btn outline block" onClick={onCancel} disabled={busy}>{t("cancel")}</button>}
      </div>
    </form>
  );
}

// --- Offres ----------------------------------------------------------------------------------------

const LIMITS = ["medical", "repatriation", "baggage", "delay", "liability"] as const;

function euros(value: number | null | undefined, lang: "fr" | "ar", t: (k: Key) => string): string {
  if (value === null) return t("actualCosts");
  if (value === undefined) return "—";
  return `${new Intl.NumberFormat(lang === "ar" ? "ar-MR" : "fr-FR").format(value)} €`;
}

/** Garanties et plafonds (en euros) d'une offre voyage. `short` : les trois principales. */
export function LimitsList({ limits, short = false }: { limits: TravelLimits; short?: boolean }) {
  const { t, lang } = useI18n();
  return (
    <dl className="limits">
      {(short ? LIMITS.slice(0, 3) : LIMITS).map((code) => (
        <div key={code}>
          <dt>{t(`limit_${code}` as Key)}</dt>
          <dd>{euros(limits[code], lang, t)}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Offres voyage comparées : prix total, plafonds principaux, toutes les garanties de l'offre choisie. */
export function TravelOffers({ quotes, picked, onPick, footer }: {
  quotes: Quote[];
  picked: number | null;
  onPick: (id: number) => void;
  footer?: ReactNode;
}) {
  const { t, lang } = useI18n();
  const first = quotes[0];
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="stack" role="radiogroup" aria-label={t("quotesTitle")}>
        {quotes.map((q) => {
          const on = q.id === picked;
          return (
            <button key={q.id} type="button" role="radio" aria-checked={on} className={`card${on ? " selected" : ""}`}
              onClick={() => onPick(q.id)}>
              <div className="row">
                <InsurerLogo name={q.insurer} logo={q.insurer_logo} size={48} selected={on} />
                <div className="grow stack" style={{ gap: 2 }}>
                  <strong style={{ fontSize: 16 }}>{q.insurer}</strong>
                  <span className="ink2" style={{ fontSize: 13 }}>{q.product}</span>
                </div>
                <div className="stack" style={{ gap: 4, alignItems: "flex-end" }}>
                  <span className="price">{money(q.premium, lang)}</span>
                  {q.indicative && <span className="small muted">{t("indicative")}</span>}
                </div>
              </div>
              <LimitsList limits={q.limits} short={!on} />
            </button>
          );
        })}
      </div>
      {first && first.travelers !== null && first.days !== null && (
        <span className="small muted" style={{ textAlign: "center" }}>
          {t("travelPrice", { travelers: t("travelersCount", { count: first.travelers }), days: t("tripDays", { count: first.days }) })}
        </span>
      )}
      <p className="note" style={{ margin: 0 }}>
        <Icon name="shield" size={16} strokeWidth={2} />
        {t("schengenNote")}
      </p>
      {quotes.some((q) => q.indicative) && (
        <p className="note" style={{ margin: 0, justifyContent: "center", textAlign: "center" }}>{t("indicativeNote")}</p>
      )}
      {footer}
    </div>
  );
}

/** Numéro d'assistance 24 h/24, cliquable. */
export function AssistanceLink({ phone, insurer }: { phone: string; insurer: string }) {
  const { t } = useI18n();
  if (!phone) return null;
  return (
    <a className="btn outline block assistance" href={`tel:${phone.replace(/\s/g, "")}`} aria-label={`${t("callAssistance")} · ${insurer} · ${phone}`}>
      <Icon name="phone" size={20} strokeWidth={2} />
      <span className="stack" style={{ gap: 0, alignItems: "flex-start" }}>
        <small>{t("assistance24")}</small>
        <bdi dir="ltr">{phone}</bdi>
      </span>
    </a>
  );
}
