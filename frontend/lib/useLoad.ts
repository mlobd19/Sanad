"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "./api";

/** Charge `path` et le recharge à la demande ; les données d'un autre chemin ne sont jamais affichées. */
export function useLoad<T>(path: string | null) {
  const [loaded, setLoaded] = useState<{ path: string; data: T } | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    if (!path) return;
    setError("");
    try {
      const data = await api<T>(path);
      setLoaded({ path, data });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "error");
    }
  }, [path]);
  useEffect(() => {
    reload();
  }, [reload]);
  return { data: loaded && loaded.path === path ? loaded.data : null, error, reload };
}
