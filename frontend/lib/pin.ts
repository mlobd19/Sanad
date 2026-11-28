// Code PIN à 4 chiffres des particuliers. Le serveur vérifie et décide (backend : accounts/pin.py) ;
// ce fichier ne garde jamais le code : ni stockage du navigateur, ni journal.

export const PIN_LENGTH = 4;

/** Entier aléatoire dans [0, n), tiré par crypto.getRandomValues, sans biais (tirages hors limite rejetés). */
function randomBelow(n: number): number {
  const buffer = new Uint32Array(1);
  const limit = Math.floor(0x1_0000_0000 / n) * n;
  do crypto.getRandomValues(buffer);
  while (buffer[0] >= limit);
  return buffer[0] % n;
}

/** Les chiffres 0 à 9 dans un ordre aléatoire (mélange de Fisher-Yates). */
export function shuffledDigits(): string[] {
  const digits = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"];
  for (let i = digits.length - 1; i > 0; i--) {
    const j = randomBelow(i + 1);
    [digits[i], digits[j]] = [digits[j], digits[i]];
  }
  return digits;
}

/**
 * Codes trop simples, refusés avant même la confirmation (mêmes règles que le serveur, qui refuse aussi
 * les 4 derniers chiffres du numéro) : 4 chiffres identiques, suites (1234, 4321, 0123…), paires
 * répétées (1212, 2020), années de 1940 à l'année en cours.
 */
export function tooSimplePin(pin: string): boolean {
  const d = pin.split("").map(Number);
  const steps = new Set(d.slice(1).map((x, i) => x - d[i]));
  if (new Set(d).size === 1) return true;
  if (steps.size === 1 && (steps.has(1) || steps.has(-1))) return true;
  if (pin.slice(0, 2) === pin.slice(2)) return true;
  const year = Number(pin);
  return year >= 1940 && year <= new Date().getFullYear();
}

/** Réponse de GET /api/auth/pin : état de cet appareil et nom du client. */
export type PinStatus = {
  /** setup : code à choisir (compte sans code) ; verify : nouvel appareil, après le SMS, code du compte à
   *  saisir (ou nouveau code si oublié) ; locked : code à saisir ; open : session ouverte. */
  state: "setup" | "verify" | "locked" | "open";
  attempts_left: number;
  full_name: string;
  full_name_ar: string;
  phone_end: string;
};
