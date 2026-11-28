"use client";

import { useState } from "react";

import { groupPhone, localPhone } from "@/lib/format";

/** Saisie d'un numéro mauritanien : 8 chiffres groupés par deux (36 00 00 01), sans indicatif
 *  (Sanad n'existe qu'en Mauritanie). `value` et `onChange` portent les 8 chiffres ; l'appelant
 *  envoie `+222${value}`. Un « +222 » collé est retiré par `localPhone`. Aligné à droite en arabe. */
export function PhoneInput({ id, value, onChange, autoComplete = "tel-national", describedBy, required = true }: {
  id: string;
  value: string;
  onChange: (digits: string) => void;
  autoComplete?: string;
  describedBy?: string;
  required?: boolean;
}) {
  // Indicatif tapé par habitude (« +222 » ou « 00222 ») : affiché tel quel le temps de la frappe, puis retiré.
  const [typingCode, setTypingCode] = useState<string | null>(null);

  function change(text: string) {
    if (/^\s*(\+|00)/.test(text)) {
      const digits = text.replace(/\D/g, "").replace(/^00/, "");
      if ("222".startsWith(digits)) { setTypingCode(text); onChange(""); return; }
      if (digits.startsWith("222")) { setTypingCode(null); onChange(digits.slice(3, 11)); return; }
    }
    setTypingCode(null);
    onChange(localPhone(text));
  }

  return (
    <input
      id={id}
      dir="ltr"
      className="input"
      type="tel"
      inputMode="numeric"
      autoComplete={autoComplete}
      value={typingCode ?? groupPhone(value)}
      onChange={(e) => change(e.target.value)}
      aria-describedby={describedBy}
      style={{ fontWeight: 600, letterSpacing: "0.04em" }}
      required={required}
    />
  );
}
