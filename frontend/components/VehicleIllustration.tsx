import { useId } from "react";

/** Type de carrosserie déduit de la marque et du modèle (backend : policies/body_types.py). */
export type BodyType = "sedan" | "city" | "suv" | "pickup" | "van" | "minibus" | "generic";

export const BODY_TYPES: BodyType[] = ["sedan", "city", "suv", "pickup", "van", "minibus", "generic"];

type Shape = {
  /** Caisse, vue de profil, avant à droite. Passages de roue découpés dans le tracé. */
  body: string;
  /** Vitres latérales et pare-brise. */
  windows: string[];
  /** Centre des roues (x) ; toutes sur la même ligne. */
  wheels: [number, number];
  /** Reflet métallique le long de la ligne de caisse. */
  shine: string;
  /** Détails de carrosserie (portes, ridelle, barres de toit), en trait fin. */
  details?: string[];
  /** Barres de toit (4x4), en trait plein. */
  roofRails?: string;
  /** Phare (avant) et feu (arrière). */
  lights: { front: string; rear: string };
};

// Silhouettes originales, volontairement génériques : aucune ne reprend le dessin d'un modèle existant.
// Repère commun : viewBox 0 0 240 112, sol à y = 104, roues de rayon 16 centrées à y = 88.
const SHAPES: Record<BodyType, Shape> = {
  sedan: {
    body: "M14 80 L14 67 Q16 60 26 59 L62 56 L84 39 Q88 35 96 35 L142 35 Q150 35 156 41 L176 56 L214 60 Q226 62 228 72 L228 82 Q228 86 224 86 L208 86 A18 18 0 0 0 172 86 L74 86 A18 18 0 0 0 38 86 L20 86 Q14 86 14 80 Z",
    windows: ["M88 54 L99 42 Q101 40 105 40 L119 40 L119 54 Z", "M125 40 L141 40 Q146 40 150 44 L161 54 L125 54 Z"],
    wheels: [56, 190],
    shine: "M22 64 Q120 60 220 66",
    details: ["M122 56 L122 82", "M76 60 L76 82"],
    lights: { front: "M218 64 Q225 66 226 71 L214 70 Z", rear: "M15 64 L22 63 L22 69 L15 70 Z" },
  },
  city: {
    body: "M32 82 L32 58 Q32 46 44 42 L62 34 Q66 32 72 32 L128 32 Q136 32 142 38 L162 54 L196 58 Q208 60 210 70 L210 82 Q210 86 206 86 L194 86 A17 17 0 0 0 160 86 L84 86 A17 17 0 0 0 50 86 L36 86 Q32 86 32 82 Z",
    windows: ["M44 54 Q44 47 52 43 L66 37 L94 37 L94 54 Z", "M100 37 L127 37 Q133 37 137 41 L151 54 L100 54 Z"],
    wheels: [67, 177],
    shine: "M38 63 Q120 59 204 65",
    details: ["M97 56 L97 82"],
    lights: { front: "M200 62 Q207 64 208 69 L197 68 Z", rear: "M33 58 L39 57 L39 66 L33 67 Z" },
  },
  suv: {
    body: "M14 82 L14 32 Q14 24 24 24 L148 22 Q155 22 160 27 L178 46 L216 50 Q228 52 228 62 L228 82 Q228 86 224 86 L210 86 A19 19 0 0 0 172 86 L72 86 A19 19 0 0 0 34 86 L18 86 Q14 86 14 82 Z",
    windows: ["M22 30 L56 29 L56 46 L22 46 Z", "M62 29 L104 28 L104 46 L62 46 Z", "M110 28 L146 28 Q151 28 154 32 L166 46 L110 46 Z"],
    wheels: [53, 191],
    shine: "M20 56 Q120 52 222 58",
    details: ["M107 48 L107 82", "M59 48 L59 82"],
    roofRails: "M32 24 L32 18 L134 17 L134 22.5",
    lights: { front: "M218 54 Q225 56 226 61 L214 60 Z", rear: "M14 40 L20 40 L20 50 L14 50 Z" },
  },
  pickup: {
    body: "M12 82 L12 50 L96 50 L96 30 Q96 24 102 24 L146 24 Q153 24 158 30 L174 48 L214 52 Q226 54 228 64 L228 82 Q228 86 224 86 L210 86 A19 19 0 0 0 172 86 L78 86 A19 19 0 0 0 40 86 L16 86 Q12 86 12 82 Z",
    windows: ["M102 30 L123 30 L123 46 L102 46 Z", "M129 30 L146 30 Q151 30 154 34 L164 46 L129 46 Z"],
    wheels: [59, 191],
    shine: "M18 60 Q120 56 222 62",
    details: ["M14 55 L94 55", "M126 48 L126 82"],
    lights: { front: "M218 56 Q225 58 226 63 L214 62 Z", rear: "M12 54 L18 54 L18 64 L12 64 Z" },
  },
  van: {
    body: "M12 82 L12 26 Q12 18 20 18 L160 18 Q168 18 172 24 L190 46 L216 52 Q228 55 228 66 L228 82 Q228 86 224 86 L210 86 A19 19 0 0 0 172 86 L70 86 A19 19 0 0 0 32 86 L16 86 Q12 86 12 82 Z",
    windows: ["M148 26 L163 26 Q167 26 170 30 L183 46 L148 46 Z"],
    wheels: [51, 191],
    shine: "M18 58 Q120 54 222 60",
    details: ["M98 22 L98 82", "M144 22 L144 82", "M88 60 L94 60"],
    lights: { front: "M218 58 Q225 60 226 65 L214 64 Z", rear: "M12 34 L18 34 L18 46 L12 46 Z" },
  },
  minibus: {
    body: "M10 82 L10 24 Q10 16 18 16 L178 16 Q188 16 194 26 L208 48 L220 52 Q230 56 230 66 L230 82 Q230 86 226 86 L212 86 A18 18 0 0 0 176 86 L64 86 A18 18 0 0 0 28 86 L14 86 Q10 86 10 82 Z",
    windows: [
      "M18 24 L44 24 L44 44 L18 44 Z", "M50 24 L78 24 L78 44 L50 44 Z", "M84 24 L112 24 L112 44 L84 44 Z",
      "M118 24 L146 24 L146 44 L118 44 Z", "M152 24 L174 24 L174 44 L152 44 Z",
      "M180 24 Q186 24 190 30 L200 44 L180 44 Z",
    ],
    wheels: [46, 194],
    shine: "M16 56 Q120 52 224 58",
    details: ["M149 46 L149 82", "M115 46 L115 82"],
    lights: { front: "M220 58 Q227 60 228 65 L216 64 Z", rear: "M10 30 L16 30 L16 42 L10 42 Z" },
  },
  generic: {
    body: "M18 82 L18 62 Q18 54 28 52 L56 48 Q72 32 96 30 L140 30 Q160 30 176 46 L210 54 Q224 57 224 70 L224 82 Q224 86 220 86 L206 86 A18 18 0 0 0 170 86 L76 86 A18 18 0 0 0 40 86 L22 86 Q18 86 18 82 Z",
    windows: ["M66 48 Q78 36 98 36 L118 36 L118 48 Z", "M124 36 L140 36 Q154 36 166 48 L124 48 Z"],
    wheels: [58, 188],
    shine: "M26 60 Q120 56 216 62",
    details: ["M121 50 L121 82"],
    lights: { front: "M212 60 Q220 62 222 67 L209 66 Z", rear: "M19 60 L25 59 L25 66 L19 67 Z" },
  },
};

const OUTLINE = "#2e363b";

/**
 * Illustration du véhicule, toujours en gris métallisé (aucune couleur ni logo de constructeur).
 * Décorative par défaut ; passer `label` pour l'annoncer aux lecteurs d'écran.
 */
export function VehicleIllustration({ type, width = 120, label }: { type?: string | null; width?: number; label?: string }) {
  const shape = SHAPES[(type as BodyType) in SHAPES ? (type as BodyType) : "generic"];
  const id = useId().replace(/:/g, "");
  const metal = `metal-${id}`;
  const glass = `glass-${id}`;
  const rim = `rim-${id}`;
  return (
    <svg
      className="vehicle-illustration"
      width={width}
      height={(width * 112) / 240}
      viewBox="0 0 240 112"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      <defs>
        <linearGradient id={metal} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#f2f4f5" />
          <stop offset="0.35" stopColor="#c9cfd3" />
          <stop offset="0.55" stopColor="#9aa3a9" />
          <stop offset="0.72" stopColor="#b7bec3" />
          <stop offset="1" stopColor="#7d868c" />
        </linearGradient>
        <linearGradient id={glass} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#52606a" />
          <stop offset="0.6" stopColor="#7a8790" />
          <stop offset="1" stopColor="#a9b3ba" />
        </linearGradient>
        <radialGradient id={rim} cx="0.4" cy="0.35" r="0.7">
          <stop offset="0" stopColor="#eef0f1" />
          <stop offset="1" stopColor="#8e979d" />
        </radialGradient>
      </defs>
      <ellipse cx="120" cy="105" rx="108" ry="4" fill="#000" opacity="0.16" />
      {/* Halo clair : le contour reste lisible sur fond sombre (quasi invisible sur fond clair). */}
      <g fill="none" stroke="#fff" strokeWidth="5" strokeLinejoin="round" opacity="0.35">
        <path d={shape.body} />
        {shape.wheels.map((x) => <circle key={x} cx={x} cy="88" r="16" />)}
      </g>
      <path d={shape.body} fill={`url(#${metal})`} stroke={OUTLINE} strokeWidth="2.2" strokeLinejoin="round" />
      {shape.windows.map((d) => (
        <path key={d} d={d} fill={`url(#${glass})`} stroke={OUTLINE} strokeWidth="1.6" strokeLinejoin="round" />
      ))}
      {shape.details?.map((d) => (
        <path key={d} d={d} fill="none" stroke={OUTLINE} strokeWidth="1.2" strokeLinecap="round" opacity="0.55" />
      ))}
      {shape.roofRails && (
        <path d={shape.roofRails} fill="none" stroke={OUTLINE} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      )}
      <path d={shape.shine} fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" opacity="0.7" />
      <path d={shape.lights.front} fill="#f7f8f8" stroke={OUTLINE} strokeWidth="1.2" strokeLinejoin="round" />
      <path d={shape.lights.rear} fill="#6b7378" stroke={OUTLINE} strokeWidth="1.2" strokeLinejoin="round" />
      {shape.wheels.map((x) => (
        <g key={x}>
          <circle cx={x} cy="88" r="16" fill="#2b3236" stroke={OUTLINE} strokeWidth="2" />
          <circle cx={x} cy="88" r="9" fill={`url(#${rim})`} stroke="#5b646a" strokeWidth="1.2" />
          <circle cx={x} cy="88" r="2.6" fill="#5b646a" />
        </g>
      ))}
    </svg>
  );
}
