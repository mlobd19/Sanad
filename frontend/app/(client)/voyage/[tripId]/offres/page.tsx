"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useNav } from "@/components/NavLink";
import { ErrorBox, ErrorLine } from "@/components/Shell";
import { QuotesSkeleton } from "@/components/Skeletons";
import { TravelOffers, TripSummary, useTravelError } from "@/components/Travel";
import { api, type Policy, type Quote, type Trip } from "@/lib/api";
import { cache } from "@/lib/cache";
import { money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useSpace } from "@/lib/spaces";
import { prefetch, useLoad } from "@/lib/useLoad";

/** Assurance voyage, étape 3 : offres comparées (prix total, plafonds), puis contrat et paiement. */
export default function TravelQuotesPage() {
  const { t, lang } = useI18n();
  const nav = useNav();
  const travelError = useTravelError();
  const { tripId } = useParams<{ tripId: string }>();
  const { user } = useSpace("customer");
  const trip = useLoad<Trip>(`trips/${tripId}`, !!user).data;
  const key = `quotes/trip/${tripId}`;
  const [quotes, setQuotes] = useState<Quote[] | null>(() => cache.get<Quote[]>(key) ?? null);
  const [picked, setPicked] = useState<number | null>(() => quotes?.[0]?.id ?? null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setError("");
    api<Quote[]>(`trips/${tripId}/quotes`, { method: "POST" })
      .then((qs) => {
        cache.set(key, qs);
        setQuotes(qs);
        setPicked((current) => {
          const insurer = qs.find((q) => q.id === current)?.insurer_slug;
          return (qs.find((q) => q.insurer_slug === insurer) ?? qs[0])?.id ?? null;
        });
      })
      .catch((err) => setError(travelError(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripId, key]);

  useEffect(() => {
    if (user) {
      load();
      prefetch("payments/providers");
    }
  }, [user, load]);

  async function proceed() {
    if (!picked) return;
    setBusy(true);
    setError("");
    try {
      const policy = await api<Policy>("policies", { body: { quote_id: picked } });
      cache.set(`policies/${policy.id}`, policy);
      nav.push(`/paiement/${policy.id}`);
    } catch (err) {
      setError(travelError(err));
      setBusy(false);
    }
  }

  const chosen = quotes?.find((q) => q.id === picked);
  return (
    <>
      <main className="content">
        {trip && <p className="small ink2" style={{ margin: 0 }}><TripSummary trip={trip} travelers={trip.travelers.length} /></p>}
        {!quotes && !error && <QuotesSkeleton vehicle={false} />}
        {!quotes && error && <ErrorBox message={error} onRetry={load} />}
        {quotes && quotes.length === 0 && <p className="ink2">{t("noTravelQuotes")}</p>}
        {quotes && quotes.length > 0 && <TravelOffers quotes={quotes} picked={picked} onPick={setPicked} />}
      </main>
      {quotes && quotes.length > 0 && (
        <div className="footer-cta">
          <ErrorLine message={quotes ? error : ""} />
          <button type="button" className="btn primary block tall split" onClick={proceed} disabled={!picked || busy}>
            <span>{t("continue")}</span>
            {chosen && <span>{money(chosen.premium, lang)}</span>}
          </button>
        </div>
      )}
    </>
  );
}
