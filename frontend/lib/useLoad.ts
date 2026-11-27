"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError, type Policy } from "./api";
import { cache } from "./cache";

/**
 * Charge `path` (GET) et le recharge à la demande. Les dernières données lues pour ce chemin
 * (lib/cache.ts) s'affichent tout de suite, pendant l'actualisation : plus d'écran vide au retour
 * sur un écran déjà vu. Les données d'un autre chemin ne sont jamais affichées.
 * `enabled` : faux tant que le compte n'est pas confirmé (aucune requête, mais le cache s'affiche).
 */
export function useLoad<T>(path: string | null, enabled = true) {
  const [loaded, setLoaded] = useState<{ path: string; data: T } | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    if (!path || !enabled) return;
    setError("");
    try {
      const data = await api<T>(path);
      cache.set(path, data);
      setLoaded({ path, data });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "error");
    }
  }, [path, enabled]);
  useEffect(() => {
    reload();
  }, [reload]);
  /** Remplace les données affichées (après une action), cache compris. */
  const mutate = useCallback(
    (data: T) => {
      if (!path) return;
      cache.set(path, data);
      setLoaded({ path, data });
    },
    [path],
  );
  const fresh = loaded && loaded.path === path ? loaded.data : null;
  const data = fresh ?? (path ? cache.get<T>(path) ?? null : null);
  return { data, error, reload, mutate };
}

/** Contrat déjà connu : lu seul (`policies/<id>`) ou dans la liste des contrats (même forme). */
export function cachedPolicy(id: string | number): Policy | null {
  return (
    cache.get<Policy>(`policies/${id}`) ??
    cache.get<Policy[]>("policies")?.find((p) => String(p.id) === String(id)) ??
    null
  );
}

/** Précharge en arrière-plan les données de l'écran suivant probable (ex. véhicules depuis l'accueil),
 *  pour qu'il s'affiche complet, sans contenu qui arrive après coup. */
export function prefetch(path: string) {
  if (cache.get(path) !== undefined) return;
  api(path).then((data) => cache.set(path, data)).catch(() => undefined);
}
