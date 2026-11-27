"use client";

import { useRef, useState, type FormEvent } from "react";

import { Icon } from "@/components/Icon";
import { AssistanceLink } from "@/components/Travel";
import { ApiError, apiUpload, type Claim, type ClaimKind, type Policy } from "@/lib/api";
import { destinationsLabel } from "@/lib/countries";
import { formatPlate, plateInput } from "@/lib/format";
import { useI18n, type Key } from "@/lib/i18n";

const KINDS: ClaimKind[] = ["accident", "theft", "fire", "glass", "other"];
// Voyage : mêmes étapes de déclaration, autres types de sinistre (comme Claim.TRAVEL_KINDS côté serveur).
const TRAVEL_KINDS: ClaimKind[] = ["medical", "repatriation", "baggage", "delay", "theft", "other"];
const MAX_PHOTOS = 6;
const MAX_BYTES = 8 * 1024 * 1024;

/** Formulaire de déclaration de sinistre, partagé par l'app client et l'espace entreprise.
 *  `endpoint` : policies/<id>/claims (particulier) ou company/policies/<id>/claims (flotte). */
export function ClaimForm<T extends Claim = Claim>({ policy, endpoint, onSent, onCancel }: {
  policy: Pick<Policy, "id" | "plate" | "insurer" | "product" | "starts_on" | "ends_on">
    & Partial<Pick<Policy, "trip" | "assistance_phone">>;
  endpoint: string;
  onSent: (claim: T) => void;
  onCancel?: () => void;
}) {
  const { t, lang } = useI18n();
  const trip = policy.trip ?? null;
  const today = new Date().toISOString().slice(0, 10);
  const maxDate = policy.ends_on < today ? policy.ends_on : today;
  const ids = `claim-${policy.id}`;

  const [kind, setKind] = useState<ClaimKind | "">("");
  const [occurredOn, setOccurredOn] = useState(maxDate);
  const [place, setPlace] = useState("");
  const [description, setDescription] = useState("");
  const [thirdParty, setThirdParty] = useState("");
  const [injuries, setInjuries] = useState(false);
  const [traveler, setTraveler] = useState<number | null>(trip?.travelers.length === 1 ? trip.travelers[0].id : null);
  const [photos, setPhotos] = useState<File[]>([]);
  const photoInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Key | "">("");

  function addPhotos(files: FileList | null) {
    const picked = Array.from(files ?? []);
    if (picked.some((f) => f.size > MAX_BYTES)) setError("claimErr_too_large");
    else if (photos.length + picked.length > MAX_PHOTOS) setError("claimErr_too_many_photos");
    else setError("");
    setPhotos((list) => [...list, ...picked.filter((f) => f.size <= MAX_BYTES)].slice(0, MAX_PHOTOS));
    if (photoInput.current) photoInput.current.value = "";
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!kind) return setError("claimErr_invalid_kind");
    if (!place.trim() || !description.trim()) return setError("claimErr_missing_fields");
    setBusy(true);
    setError("");
    const form = new FormData();
    form.append("kind", kind);
    form.append("occurred_on", occurredOn);
    form.append("place", place);
    form.append("description", description);
    form.append("third_party_plate", thirdParty);
    form.append("injuries", injuries ? "true" : "false");
    if (traveler) form.append("traveler", String(traveler));
    photos.forEach((f) => form.append("photos", f));
    try {
      onSent(await apiUpload<T>(endpoint, form));
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "";
      setError(code ? (`claimErr_${code}` as Key) : "error");
      setBusy(false);
    }
  }

  return (
    <form className="stack" style={{ gap: 18 }} onSubmit={submit} noValidate>
      {trip ? (
        <>
          {/* Urgence : l'assistance d'abord (prise en charge directe des frais), la déclaration ensuite. */}
          <div className="banner sand" role="note" style={{ flexDirection: "column", alignItems: "stretch", gap: 10 }}>
            <strong style={{ fontSize: 14 }}>{t("claimAssistanceFirst", { insurer: policy.insurer })}</strong>
            <AssistanceLink phone={policy.assistance_phone ?? ""} insurer={policy.insurer} />
          </div>
          <p className="small ink2" style={{ margin: 0 }}>
            {destinationsLabel(trip.destinations, lang, 3)} · {policy.insurer} · {policy.product}
          </p>
        </>
      ) : (
        <p className="small ink2" style={{ margin: 0 }}>
          <bdi dir="ltr">{formatPlate(policy.plate)}</bdi> · {policy.insurer} · {policy.product}
        </p>
      )}

      {trip && trip.travelers.length > 1 && (
        <fieldset className="field" style={{ border: "none", padding: 0, margin: 0 }}>
          <legend style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>{t("claimTraveler")}</legend>
          <div className="chips" role="radiogroup" aria-label={t("claimTraveler")} style={{ flexWrap: "wrap" }}>
            {trip.travelers.map((x) => (
              <button key={x.id} type="button" role="radio" aria-checked={traveler === x.id} onClick={() => setTraveler(x.id)}>
                {lang === "ar" && x.full_name_ar ? x.full_name_ar : x.full_name}
              </button>
            ))}
          </div>
        </fieldset>
      )}

      <fieldset className="field" style={{ border: "none", padding: 0, margin: 0 }}>
        <legend style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>{t("claimKind")}</legend>
        <div className="chips" role="radiogroup" aria-label={t("claimKind")} style={{ flexWrap: "wrap" }}>
          {(trip ? TRAVEL_KINDS : KINDS).map((k) => (
            <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => setKind(k)}>
              {t(`claimKind_${k}` as Key)}
            </button>
          ))}
        </div>
      </fieldset>

      {!trip && <fieldset className="field" style={{ border: "none", padding: 0, margin: 0 }}>
        <legend style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>{t("claimInjuries")}</legend>
        <div className="segmented" style={{ gridTemplateColumns: "1fr 1fr" }} role="radiogroup" aria-label={t("claimInjuries")}>
          {[true, false].map((v) => (
            <button key={String(v)} type="button" role="radio" aria-checked={injuries === v} className="radio"
              style={{ justifyContent: "center", minHeight: 48 }} onClick={() => setInjuries(v)}>
              {t(v ? "yes" : "no")}
            </button>
          ))}
        </div>
        {injuries && <p className="banner red" role="alert" style={{ margin: "8px 0 0" }}>{t("claimInjuriesWarning")}</p>}
      </fieldset>}

      <div className="field">
        <label htmlFor={`${ids}-date`}>{t("claimDate")}</label>
        <input id={`${ids}-date`} className="input" type="date" value={occurredOn} min={policy.starts_on} max={maxDate}
          onChange={(e) => setOccurredOn(e.target.value)} autoComplete="off" required />
      </div>

      <div className="field">
        <label htmlFor={`${ids}-place`}>{t("claimPlace")}</label>
        <input id={`${ids}-place`} className="input" value={place} maxLength={200} onChange={(e) => setPlace(e.target.value)} autoComplete="off"
          aria-describedby={`${ids}-place-hint`} required />
        <span id={`${ids}-place-hint`} className="small muted">{t("claimPlaceHint")}</span>
      </div>

      <div className="field">
        <label htmlFor={`${ids}-description`}>{t("claimDescription")}</label>
        <textarea id={`${ids}-description`} className="input" value={description} maxLength={2000}
          onChange={(e) => setDescription(e.target.value)} autoComplete="off" aria-describedby={`${ids}-description-hint`} required />
        <span id={`${ids}-description-hint`} className="small muted">{t("claimDescriptionHint")}</span>
      </div>

      {!trip && (
        <div className="field">
          <label htmlFor={`${ids}-third-party`}>{t("claimThirdParty")}</label>
          <input id={`${ids}-third-party`} className="input" dir="ltr" value={thirdParty} maxLength={40}
            onChange={(e) => setThirdParty(plateInput(e.target.value))} autoCapitalize="characters" autoComplete="off" spellCheck={false} />
        </div>
      )}

      <div className="field">
        <span id={`${ids}-photos-label`} style={{ fontWeight: 600, fontSize: 14 }}>{t(trip ? "claimProofs" : "claimPhotos")}</span>
        <input ref={photoInput} type="file" accept="image/jpeg,image/png,application/pdf" multiple hidden
          onChange={(e) => addPhotos(e.target.files)} />
        {photos.length > 0 && (
          <ul className="stack" style={{ gap: 6, listStyle: "none", padding: 0, margin: 0 }} aria-labelledby={`${ids}-photos-label`}>
            {photos.map((f, i) => (
              <li key={`${f.name}-${i}`} className="between small">
                <bdi style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.name}</bdi>
                <button type="button" className="btn link" aria-label={t("claimRemovePhoto", { name: f.name })}
                  onClick={() => setPhotos((list) => list.filter((_, j) => j !== i))}>
                  <Icon name="close" size={18} strokeWidth={2} />
                </button>
              </li>
            ))}
          </ul>
        )}
        {photos.length < MAX_PHOTOS && (
          <button type="button" className="btn outline block" onClick={() => photoInput.current?.click()}
            aria-describedby={`${ids}-photos-hint`}>
            <Icon name="plus" size={20} strokeWidth={2} />
            {t("claimAddPhotos")}
          </button>
        )}
        <span id={`${ids}-photos-hint`} className="small muted">{t("claimPhotosHint")} {t("claimPhotosPrivacy")}</span>
      </div>

      <div aria-live="polite">{error && <p className="banner red" role="alert" style={{ margin: 0 }}>{t(error)}</p>}</div>

      <div className="stack" style={{ gap: 8 }}>
        <button className="btn primary block tall" disabled={busy}>
          {busy ? <span className="spinner sm" aria-hidden="true" /> : null}
          {busy ? t("claimSending") : t("claimSubmit")}
        </button>
        {onCancel && <button type="button" className="btn outline block" onClick={onCancel} disabled={busy}>{t("cancel")}</button>}
      </div>
    </form>
  );
}
