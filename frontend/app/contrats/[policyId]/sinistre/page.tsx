"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { Icon } from "@/components/Icon";
import { App, ErrorBox, Loading, TopBar, useUser } from "@/components/Shell";
import { api, ApiError, apiUpload, type Claim, type ClaimKind, type Policy } from "@/lib/api";
import { useI18n, type Key } from "@/lib/i18n";

const KINDS: ClaimKind[] = ["accident", "theft", "fire", "glass", "other"];
const MAX_PHOTOS = 6;
const MAX_BYTES = 8 * 1024 * 1024;

export default function DeclareClaimPage() {
  const { t } = useI18n();
  const { policyId } = useParams<{ policyId: string }>();
  const { user } = useUser();
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [loadError, setLoadError] = useState("");
  const today = new Date().toISOString().slice(0, 10);

  const [kind, setKind] = useState<ClaimKind | "">("");
  const [occurredOn, setOccurredOn] = useState(today);
  const [place, setPlace] = useState("");
  const [description, setDescription] = useState("");
  const [thirdParty, setThirdParty] = useState("");
  const [injuries, setInjuries] = useState(false);
  const [photos, setPhotos] = useState<File[]>([]);
  const photoInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Key | "">("");
  const [sent, setSent] = useState<Claim | null>(null);

  useEffect(() => {
    if (user) api<Policy>(`policies/${policyId}`).then(setPolicy).catch((e) => setLoadError(e.message));
  }, [user, policyId]);

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
    photos.forEach((f) => form.append("photos", f));
    try {
      setSent(await apiUpload<Claim>(`policies/${policyId}/claims`, form));
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "";
      setError(code ? (`claimErr_${code}` as Key) : "error");
      setBusy(false);
    }
  }

  const header = <TopBar title={t("declareClaim")} back={`/contrats/${policyId}`} />;
  if (!policy && !loadError) return <App>{header}<Loading /></App>;
  if (loadError || !policy) return <App>{header}<main className="content"><ErrorBox message={loadError} /></main></App>;

  if (sent) {
    return (
      <App>
        {header}
        <main className="content">
          <div className="banner green" role="status" style={{ flexDirection: "column", alignItems: "stretch", gap: 12 }}>
            <strong>{t("claimSent", { number: sent.number, insurer: policy.insurer })}</strong>
            <Link className="btn primary block" href={`/contrats/${policyId}`}>{t("seeDetails")}</Link>
          </div>
        </main>
      </App>
    );
  }

  if (policy.status !== "active" && policy.status !== "expired") {
    return <App>{header}<main className="content"><p className="banner sand">{t("claimErr_policy_inactive")}</p></main></App>;
  }

  const maxDate = policy.ends_on < today ? policy.ends_on : today;

  return (
    <App>
      {header}
      <form className="content stack" style={{ gap: 18 }} onSubmit={submit} noValidate>
        <p className="small ink2" style={{ margin: 0 }}>
          <bdi>{policy.plate}</bdi> · {policy.insurer} · {policy.product}
        </p>

        <fieldset className="field" style={{ border: "none", padding: 0, margin: 0 }}>
          <legend style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>{t("claimKind")}</legend>
          <div className="chips" role="radiogroup" aria-label={t("claimKind")} style={{ flexWrap: "wrap" }}>
            {KINDS.map((k) => (
              <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => setKind(k)}>
                {t(`claimKind_${k}` as Key)}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className="field" style={{ border: "none", padding: 0, margin: 0 }}>
          <legend style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>{t("claimInjuries")}</legend>
          <div className="segmented" style={{ gridTemplateColumns: "1fr 1fr" }} role="radiogroup">
            {[true, false].map((v) => (
              <button key={String(v)} type="button" role="radio" aria-checked={injuries === v} className="radio"
                style={{ justifyContent: "center", minHeight: 48 }} onClick={() => setInjuries(v)}>
                {t(v ? "yes" : "no")}
              </button>
            ))}
          </div>
          {injuries && <p className="banner red" role="alert" style={{ margin: "8px 0 0" }}>{t("claimInjuriesWarning")}</p>}
        </fieldset>

        <div className="field">
          <label htmlFor="occurred">{t("claimDate")}</label>
          <input id="occurred" className="input" type="date" value={occurredOn} min={policy.starts_on} max={maxDate}
            onChange={(e) => setOccurredOn(e.target.value)} required />
        </div>

        <div className="field">
          <label htmlFor="place">{t("claimPlace")}</label>
          <input id="place" className="input" value={place} maxLength={200} onChange={(e) => setPlace(e.target.value)}
            aria-describedby="place-hint" required />
          <span id="place-hint" className="small muted">{t("claimPlaceHint")}</span>
        </div>

        <div className="field">
          <label htmlFor="description">{t("claimDescription")}</label>
          <textarea id="description" className="input" value={description} maxLength={2000}
            onChange={(e) => setDescription(e.target.value)} aria-describedby="description-hint" required />
          <span id="description-hint" className="small muted">{t("claimDescriptionHint")}</span>
        </div>

        <div className="field">
          <label htmlFor="third-party">{t("claimThirdParty")}</label>
          <input id="third-party" className="input" dir="ltr" value={thirdParty} maxLength={40}
            onChange={(e) => setThirdParty(e.target.value.toUpperCase())} autoCapitalize="characters" />
        </div>

        <div className="field">
          <span id="photos-label" style={{ fontWeight: 600, fontSize: 14 }}>{t("claimPhotos")}</span>
          <input ref={photoInput} type="file" accept="image/jpeg,image/png,application/pdf" multiple hidden
            onChange={(e) => addPhotos(e.target.files)} />
          {photos.length > 0 && (
            <ul className="stack" style={{ gap: 6, listStyle: "none", padding: 0, margin: 0 }} aria-labelledby="photos-label">
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
              aria-describedby="photos-hint">
              <Icon name="plus" size={20} strokeWidth={2} />
              {t("claimAddPhotos")}
            </button>
          )}
          <span id="photos-hint" className="small muted">{t("claimPhotosHint")} {t("claimPhotosPrivacy")}</span>
        </div>

        <div aria-live="polite">{error && <p className="banner red" role="alert" style={{ margin: 0 }}>{t(error)}</p>}</div>

        <button className="btn primary block tall" disabled={busy}>
          {busy ? <span className="spinner sm" style={{ borderTopColor: "#fff" }} aria-hidden="true" /> : null}
          {busy ? t("claimSending") : t("claimSubmit")}
        </button>
      </form>
    </App>
  );
}
