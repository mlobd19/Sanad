"use client";

import { useParams } from "next/navigation";

import { useNav } from "@/components/NavLink";
import { ErrorBox } from "@/components/Shell";
import { FormSkeleton } from "@/components/Skeletons";
import { TravelersEditor, TripSummary } from "@/components/Travel";
import { type Trip } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSpace } from "@/lib/spaces";
import { useLoad } from "@/lib/useLoad";

/** Assurance voyage, étape 2 : les voyageurs (NNI, passeport, date de naissance). */
export default function TravelersPage() {
  const { t } = useI18n();
  const nav = useNav();
  const { tripId } = useParams<{ tripId: string }>();
  const { user } = useSpace("customer");
  const { data: trip, error, mutate } = useLoad<Trip>(`trips/${tripId}`, !!user);

  if (!trip && !error) return <main className="content"><FormSkeleton fields={3} /></main>;
  if (!trip) return <main className="content"><ErrorBox message={error} /></main>;

  return (
    <>
      <main className="content">
        <p className="small ink2" style={{ margin: 0 }}><TripSummary trip={trip} /></p>
        <TravelersEditor base="" trip={trip} onChange={mutate} me={user} max={9} />
      </main>
      <div className="footer-cta">
        <button type="button" className="btn primary block tall" disabled={!trip.travelers.length}
          onClick={() => nav.push(`/voyage/${trip.id}/offres`)}>
          {t("seeOffers")}
        </button>
      </div>
    </>
  );
}
