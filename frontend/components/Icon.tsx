// Icônes au trait, sans dépendance. currentColor pour suivre le texte.

const paths: Record<string, string> = {
  car: "M3 13l2-5h14l2 5v5H3z M7.5 18m-1.5 0a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0 -3 0 M16.5 18m-1.5 0a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0 -3 0",
  heart: "M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.5-7 10-7 10z",
  home: "M4 11l8-7 8 7v9H4z M10 20v-5h4v5",
  plane: "M2 13l20-7-7 16-3-7z",
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
  briefcase: "M3 7h18v13H3z M9 7V5h6v2",
  file: "M7 3h7l5 5v13H7z M14 3v5h5",
  user: "M12 8m-4 0a4 4 0 1 0 8 0a4 4 0 1 0 -8 0 M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6",
  back: "M15 5l-7 7 7 7",
  check: "M5 12l5 5 9-10",
  download: "M12 4v11 M7 10l5 5 5-5 M5 20h14",
  share: "M12 4v12 M7 9l5-5 5 5 M5 14v6h14v-6",
  plus: "M12 5v14 M5 12h14",
  clock: "M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0 M12 7v5l3 2",
  qr: "M4 4h6v6H4z M14 4h6v6h-6z M4 14h6v6H4z M14 14h2 M18 14h2v2 M14 18v2h6",
  expand: "M4 9V4h5 M15 4h5v5 M20 15v5h-5 M9 20H4v-5",
  close: "M6 6l12 12 M18 6L6 18",
  phone: "M8 2h8a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z M11 18h2",
};

export function Icon({ name, size = 22, strokeWidth = 1.8 }: { name: keyof typeof paths | string; size?: number; strokeWidth?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={name === "back" ? "icon flip" : "icon"}
    >
      <path d={paths[name]} />
    </svg>
  );
}
