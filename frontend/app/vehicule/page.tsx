"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { ScanRegistration } from "@/components/ScanRegistration";
import { App, Stepper, TopBar } from "@/components/Shell";
import { VehicleIllustration } from "@/components/VehicleIllustration";
import { api, ApiError, type Asset, type RegistrationScan } from "@/lib/api";
import { cleanPlate, formatPlate, plateInput } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useSpace } from "@/lib/spaces";

const USAGES = [
  { value: "personal", key: "usagePersonal" },
  { value: "commercial", key: "usageCommercial" },
  { value: "taxi", key: "usageTaxi" },
] as const;

export default function VehiclePage() {
  const { t } = useI18n();
  const router = useRouter();
  const { user } = useSpace("customer");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [plate, setPlate] = useState("");
  const [make, setMake] = useState("");
  const [power, setPower] = useState("");
  const [usage, setUsage] = useState<string>("personal");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (user) api<Asset[]>("assets").then(setAssets).catch(() => setAssets([]));
  }, [user]);

  // Champs lus sur la carte grise : seuls les champs trouvés remplacent la saisie.
  function prefill(fields: RegistrationScan) {
    if (fields.reference) setPlate(plateInput(fields.reference));
    if (fields.make) setMake(fields.make);
    if (fields.fiscal_power) setPower(String(fields.fiscal_power));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const asset = await api<Asset>("assets", {
        body: { kind: "vehicle", reference: cleanPlate(plate), attributes: { fiscal_power: Number(power), usage, make } },
      });
      router.push(`/devis/${asset.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("error"));
      setBusy(false);
    }
  }

  return (
    <App>
      <TopBar title={t("vehicleTitle")} back="/">
        <Stepper current={0} />
      </TopBar>
      <main className="content">

        {assets.length > 0 && (
          <section className="stack">
            <h2 className="eyebrow">{t("myVehicles")}</h2>
            {assets.map((a) => (
              <Link key={a.id} href={`/devis/${a.id}`} className="card" style={{ textDecoration: "none", color: "inherit" }}>
                <div className="row">
                  <VehicleIllustration type={a.body_type} width={92} />
                  <div className="grow stack" style={{ gap: 2 }}>
                    <span className="plate"><bdi dir="ltr">{formatPlate(a.reference)}</bdi></span>
                    <span className="small muted">{String(a.attributes.make || "")} {a.attributes.fiscal_power} CV</span>
                  </div>
                  <span style={{ color: "var(--green)", fontWeight: 700, fontSize: 14 }}>{t("seeQuotes")}</span>
                </div>
              </Link>
            ))}
            <h2 className="eyebrow" style={{ marginTop: 8 }}>{t("addVehicle")}</h2>
          </section>
        )}

        <form className="stack" style={{ gap: 16 }} onSubmit={submit}>
          <ScanRegistration onRead={prefill} />
          <div className="field">
            <label htmlFor="plate">{t("plate")}</label>
            <input id="plate" className="input plate-input" value={plate} onChange={(e) => setPlate(plateInput(e.target.value))}
              required dir="ltr" autoCapitalize="characters" autoComplete="off" spellCheck={false} placeholder="66 02 BA 00"
              aria-describedby="plate-hint" />
            <span id="plate-hint" className="small muted">{t("plateHint")}</span>
          </div>
          <div className="field">
            <label htmlFor="make">{t("make")}</label>
            <input id="make" className="input" value={make} onChange={(e) => setMake(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="power">{t("fiscalPower")}</label>
            <input id="power" className="input" type="number" inputMode="numeric" min={1} max={60} value={power} onChange={(e) => setPower(e.target.value)} required />
          </div>
          <fieldset className="field" style={{ border: "none", padding: 0, margin: 0 }}>
            <legend style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>{t("usage")}</legend>
            <div className="segmented" role="radiogroup">
              {USAGES.map((u) => (
                <button
                  key={u.value}
                  type="button"
                  role="radio"
                  aria-checked={usage === u.value}
                  className="radio"
                  style={{ justifyContent: "center", minHeight: 52 }}
                  onClick={() => setUsage(u.value)}
                >
                  {t(u.key)}
                </button>
              ))}
            </div>
          </fieldset>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="btn primary block tall" disabled={busy}>{t("seeQuotes")}</button>
        </form>
      </main>
    </App>
  );
}
