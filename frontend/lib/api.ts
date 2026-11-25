// Client de l'API Django. Le jeton est gardé dans le navigateur de l'utilisateur.

const TOKEN_KEY = "sanad.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* navigation privée : la session ne survit pas au rechargement */
  }
}

export class ApiError extends Error {
  status: number;
  /** Code d'erreur machine renvoyé par certaines API (ex. lecture de carte grise), traduit par l'app. */
  code: string;
  constructor(status: number, message: string, code = "") {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function errorCode(data: unknown): string {
  const code = data && typeof data === "object" ? (data as Record<string, unknown>).code : undefined;
  return typeof code === "string" ? code : "";
}

function firstMessage(data: unknown): string {
  if (!data || typeof data !== "object") return "";
  const record = data as Record<string, unknown>;
  if (typeof record.detail === "string") return record.detail;
  for (const value of Object.values(record)) {
    if (Array.isArray(value) && typeof value[0] === "string") return value[0];
    if (typeof value === "string") return value;
  }
  return "";
}

export async function api<T = unknown>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Token ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(`/api/${path}`, {
    method: options.method ?? (options.body !== undefined ? "POST" : "GET"),
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  if (response.status === 401) {
    setToken(null);
    if (typeof window !== "undefined") {
      // Session expirée : retour à la page de connexion unique, sur l'onglet de l'espace (cf. lib/spaces.ts).
      const path = window.location.pathname;
      const pro = path.startsWith("/assureur") || path.startsWith("/entreprise");
      if (!path.startsWith("/connexion")) window.location.href = pro ? "/connexion?espace=pro" : "/connexion";
    }
  }
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, firstMessage(data) || `Erreur ${response.status}`, errorCode(data));
  return data as T;
}

export async function apiBlobUrl(path: string): Promise<string> {
  const token = getToken();
  const response = await fetch(`/api/${path}`, { headers: token ? { Authorization: `Token ${token}` } : {} });
  if (!response.ok) throw new ApiError(response.status, `Erreur ${response.status}`);
  return URL.createObjectURL(await response.blob());
}

/** Envoi multipart (pièces justificatives, import CSV). */
export async function apiUpload<T = unknown>(path: string, form: FormData): Promise<T> {
  const token = getToken();
  const response = await fetch(`/api/${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Token ${token}` } : {},
    body: form,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, firstMessage(data) || `Erreur ${response.status}`, errorCode(data));
  return data as T;
}

/** Télécharge un fichier protégé (PDF…) avec le jeton de session, sous le nom donné. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const token = getToken();
  const response = await fetch(`/api/${path}`, { headers: token ? { Authorization: `Token ${token}` } : {} });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new ApiError(response.status, firstMessage(data) || `Erreur ${response.status}`, errorCode(data));
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// --- Types renvoyés par l'API -------------------------------------------------

export type User = {
  id: number;
  phone: string;
  email: string | null;
  /** Particulier : nom renvoyé par l'ANRPTS avec l'identité numérique (eID), en latin et, s'il est fourni, en arabe. */
  full_name: string;
  full_name_ar: string;
  nni: string;
  language: "fr" | "ar";
  kyc_status: "none" | "verified";
  role: string;
};

/** Durées de couverture proposées (mois). */
export const DURATIONS = [3, 6, 12] as const;
export type Months = (typeof DURATIONS)[number];

/** Carrosserie déduite de « marque et modèle » (backend : policies/body_types.py), pour l'illustration. */
export type BodyType = "sedan" | "city" | "suv" | "pickup" | "van" | "minibus" | "generic";

export type Asset = {
  id: number; kind: string; reference: string; attributes: Record<string, string | number>; body_type: BodyType;
};

export type Quote = {
  id: number;
  insurer: string;
  insurer_legal_name: string;
  insurer_slug: string;
  insurer_logo: string | null;
  product: string;
  product_code: string;
  coverages: string[];
  indicative: boolean;
  premium: number;
  duration_months: Months;
  expires_at: string;
};

export type Attestation = { id: number; number: string; status: string; issued_at: string; verify_url: string };

export type PolicyStatus = "draft" | "paid" | "active" | "refused" | "cancelled" | "expired";

export type Policy = {
  id: number;
  insurer: string;
  insurer_logo: string | null;
  product: string;
  plate: string;
  body_type: BodyType;
  premium: number;
  status: PolicyStatus;
  status_label: string;
  starts_on: string;
  ends_on: string;
  duration_months: Months;
  refusal_reason: string;
  attestation: Attestation | null;
  asset_id: number;
  renewed: boolean;
  created_at: string;
};

export type Provider = { code: string; label: string };

export type PaymentStart = { payment_id: string; reference: string; amount: number; instructions: string };

// --- Portail assureur ---------------------------------------------------------

export type InsurerMe = {
  agent: { full_name: string; phone: string };
  insurer: { name: string; legal_name: string; slug: string; logo: string | null };
};

export type InsurerPolicy = Policy & {
  customer: { full_name: string; phone: string; nni: string };
  company: { legal_name: string; nif: string; rc_number: string; status: string } | null;
  vehicle: { make: string; fiscal_power: number | null; usage: string };
  payment_provider: string | null;
  kyc_status: User["kyc_status"];
  indicative: boolean;
  insurer_reference: string;
  decided_at: string | null;
};

export type CommissionMonth = { period: string; policies: number; premiums: number; amount: number; paid: number; due: number };

export type CommissionItem = {
  id: number;
  policy_id: number;
  plate: string;
  product: string;
  premium: number;
  rate: string;
  amount: number;
  period: string;
  is_paid: boolean;
  created_at: string;
};

export type InsurerCommissions = { indicative: boolean; months: CommissionMonth[]; items: CommissionItem[] };

// --- Espace entreprise ------------------------------------------------------------------

export type CompanyStatus = "pending" | "verified" | "rejected";

export type CompanyMe = {
  company: {
    legal_name: string; nif: string; rc_number: string; address: string; status: CompanyStatus;
    rejection_reason: string; missing_documents: ("nif" | "rc")[];
    documents: { id: number; kind: "nif" | "rc"; kind_label: string; uploaded_at: string }[];
  };
  member: { full_name: string; email: string; phone: string; role: "admin" | "manager" };
};

export type CompanyMember = {
  id: number; full_name: string; email: string; phone: string; role: "admin" | "manager"; active: boolean;
  created_at: string;
};

export type Vehicle = {
  id: number;
  reference: string;
  attributes: { fiscal_power?: number; usage?: string; make?: string };
  body_type: BodyType;
  policy: { id: number; status: PolicyStatus; insurer: string; product: string; ends_on: string } | null;
};

export type GroupOffer = {
  insurer: string; insurer_legal_name: string; insurer_logo: string | null; product: string; product_code: string;
  coverages: string[]; indicative: boolean; total: number; duration_months: Months;
  lines: { asset_id: number; plate: string; quote_id: number; premium: number }[];
};

export type CompanyOrder = { id: number; total: number; created_at: string; policies: Policy[] };

export type ClaimKind = "accident" | "theft" | "fire" | "glass" | "other";
export type ClaimStatus = "submitted" | "in_review" | "closed";

/** Sinistre ; « photos » = nombre de fichiers (privés, jamais d'URL côté client). */
export type Claim = {
  id: number; number: string; kind: ClaimKind; occurred_on: string; place: string; description: string;
  third_party_plate: string; injuries: boolean; status: ClaimStatus; closing_note: string; photos: number;
  created_at: string; updated_at: string;
};

export type InsurerClaim = Claim & {
  policy: { id: number; plate: string; product: string; make: string; starts_on: string; ends_on: string; insurer_reference: string };
  /** Le déclarant ; `company` : entreprise titulaire pour un véhicule de flotte. */
  customer: { full_name: string; phone: string; company: string | null };
  photo_ids: number[];
  handled_by: string | null;
};

/** Sinistre d'un véhicule de la flotte (espace entreprise). */
export type FleetClaim = Claim & { policy_id: number; plate: string; insurer: string; declared_by: string };

/** Champs lus sur une carte grise ; vides (ou null) quand illisibles. */
export type RegistrationScan = { reference: string; make: string; fiscal_power: number | null };

export type FleetImport = { created: string[]; errors: { line: number; plate?: string; message: string }[] };
