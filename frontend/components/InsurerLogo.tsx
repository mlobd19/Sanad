import type { ReactNode } from "react";

import { Icon } from "./Icon";

/** Sigle de repli : le sigle s'il est court (NASR, CNA), sinon l'initiale du premier mot. */
export function sigle(name: string) {
  const first = name.replace(/\(.*?\)/g, "").trim().split(/\s+/)[0] ?? name;
  return /^[A-Z]{2,4}$/.test(first) ? first : first.charAt(0).toUpperCase();
}

type Props = {
  name: string;
  logo?: string | null;
  size?: number;
  selected?: boolean;
  /** Affiché à la place du sigle quand il n'y a pas de logo (ex. icône voiture). */
  fallback?: ReactNode;
};

/** Logo officiel de la compagnie sur fond blanc ; sigle (ou repli) tant qu'il n'est pas fourni. */
export function InsurerLogo({ name, logo, size = 44, selected = false, fallback }: Props) {
  const label = sigle(name);
  return (
    <span
      className={`insurer-logo${logo ? " has-logo" : ""}${selected ? " on" : ""}`}
      style={{ width: size, height: size, fontSize: label.length > 2 ? Math.round(size / 4) : Math.round(size / 2.8) }}
    >
      {logo ? <img src={logo} alt={name} /> : fallback ?? <span aria-hidden="true">{label}</span>}
      {selected && (
        <span className="insurer-check" aria-hidden="true">
          <Icon name="check" size={12} strokeWidth={3.4} />
        </span>
      )}
    </span>
  );
}
