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
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
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
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/connexion")) {
      window.location.href = "/connexion";
    }
  }
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, firstMessage(data) || `Erreur ${response.status}`);
  return data as T;
}

export async function apiBlobUrl(path: string): Promise<string> {
  const token = getToken();
  const response = await fetch(`/api/${path}`, { headers: token ? { Authorization: `Token ${token}` } : {} });
  if (!response.ok) throw new ApiError(response.status, `Erreur ${response.status}`);
  return URL.createObjectURL(await response.blob());
}

// --- Types renvoyés par l'API -------------------------------------------------

export type User = {
  id: number;
  phone: string;
  full_name: string;
  nni: string;
  language: "fr" | "ar";
  kyc_status: "none" | "pending" | "verified" | "rejected";
  role: string;
};

export type Asset = { id: number; kind: string; reference: string; attributes: Record<string, string | number> };

export type Quote = {
  id: number;
  insurer: string;
  insurer_legal_name: string;
  insurer_slug: string;
  product: string;
  product_code: string;
  coverages: string[];
  indicative: boolean;
  premium: number;
  expires_at: string;
};

export type Attestation = { id: number; number: string; status: string; issued_at: string; verify_url: string };

export type PolicyStatus = "draft" | "paid" | "active" | "refused" | "cancelled" | "expired";

export type Policy = {
  id: number;
  insurer: string;
  product: string;
  plate: string;
  premium: number;
  status: PolicyStatus;
  status_label: string;
  starts_on: string;
  ends_on: string;
  refusal_reason: string;
  attestation: Attestation | null;
  asset_id: number;
  renewed: boolean;
  created_at: string;
};

export type Provider = { code: string; label: string };

export type PaymentStart = { payment_id: string; reference: string; amount: number; instructions: string };
