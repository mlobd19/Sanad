"use client";

import { groupPhone, localPhone } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

/** Saisie d'un numéro mauritanien : « +222 » fixe puis 8 chiffres groupés par deux (36 00 00 01).
 *  `value` et `onChange` portent les 8 chiffres seuls ; l'appelant envoie `+222${value}`. */
export function PhoneInput({ id, value, onChange, autoComplete = "tel-national", describedBy, required = true }: {
  id: string;
  value: string;
  onChange: (digits: string) => void;
  autoComplete?: string;
  describedBy?: string;
  required?: boolean;
}) {
  const { t } = useI18n();
  return (
    <div className="row" style={{ gap: 8 }} dir="ltr">
      <span className="input" aria-hidden="true"
        style={{ width: "auto", display: "flex", alignItems: "center", background: "var(--bg)", fontWeight: 700 }}>
        +222
      </span>
      <input
        id={id}
        className="input"
        type="tel"
        inputMode="numeric"
        autoComplete={autoComplete}
        placeholder={t("phonePlaceholder")}
        value={groupPhone(value)}
        onChange={(e) => onChange(localPhone(e.target.value))}
        aria-describedby={describedBy}
        style={{ fontWeight: 600, letterSpacing: "0.04em" }}
        required={required}
      />
    </div>
  );
}
