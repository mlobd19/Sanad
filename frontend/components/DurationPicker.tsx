"use client";

import { DURATIONS, type Months } from "@/lib/api";
import { useI18n, type Key } from "@/lib/i18n";

export const DURATION_LABEL: Record<Months, Key> = { 3: "months3", 6: "months6", 12: "months12" };

/** Choix de la durée de couverture : 3, 6 ou 12 mois (partagé particulier / entreprise). */
export function DurationPicker({ value, onChange, disabled }: {
  value: Months; onChange: (months: Months) => void; disabled?: boolean;
}) {
  const { t } = useI18n();
  return (
    <div className="stack" style={{ gap: 6 }}>
      <span id="duration-label" className="small ink2">{t("duration")}</span>
      <div className="chips" role="group" aria-labelledby="duration-label">
        {DURATIONS.map((m) => (
          <button key={m} type="button" aria-pressed={value === m} disabled={disabled} onClick={() => onChange(m)}>
            {t(DURATION_LABEL[m])}
          </button>
        ))}
      </div>
    </div>
  );
}

export function parseMonths(value: string | null): Months {
  const n = Number(value);
  return (DURATIONS as readonly number[]).includes(n) ? (n as Months) : 12;
}
