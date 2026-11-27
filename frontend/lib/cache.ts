/**
 * Dernières données lues par chaque écran, gardées en mémoire (jamais sur le disque) : un écran
 * déjà visité s'affiche tout de suite avec elles, pendant que l'app les actualise.
 * Vidé à chaque connexion ou déconnexion (setToken) : un compte ne voit jamais les données d'un autre.
 */
const store = new Map<string, unknown>();

export const cache = {
  get<T>(key: string): T | undefined {
    return store.get(key) as T | undefined;
  },
  set<T>(key: string, value: T) {
    store.set(key, value);
  },
  clear() {
    // Images (QR) gardées sous forme d'adresse blob: : libérées avec le reste.
    for (const value of store.values()) {
      if (typeof value === "string" && value.startsWith("blob:")) URL.revokeObjectURL(value);
    }
    store.clear();
  },
};
