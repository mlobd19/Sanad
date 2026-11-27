"use client";

import { useNav } from "@/components/NavLink";
import { TripForm } from "@/components/Travel";
import { type Trip } from "@/lib/api";
import { cache } from "@/lib/cache";
import { useSpace } from "@/lib/spaces";

/** Assurance voyage, étape 1 : destination(s) et dates. Le voyage est créé côté serveur. */
export default function TripPage() {
  const nav = useNav();
  useSpace("customer");
  // Dernier voyage saisi : formulaire pré-rempli au retour sur cet écran.
  const last = cache.get<Trip>("trip/last") ?? null;
  return (
    <main className="content">
      <TripForm base="" initial={last} onCreated={(trip) => {
        cache.set(`trips/${trip.id}`, trip);
        cache.set("trip/last", trip);
        nav.push(`/voyage/${trip.id}/voyageurs`);
      }} />
    </main>
  );
}
