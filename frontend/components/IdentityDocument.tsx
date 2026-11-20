"use client";

import { useEffect, useState, type FormEvent } from "react";

import { Icon } from "@/components/Icon";
import { api, ApiError, apiUpload, type KycDocument, type User } from "@/lib/api";
import { date } from "@/lib/format";
import { useI18n, type Key } from "@/lib/i18n";

const KINDS: { value: KycDocument["kind"]; key: Key }[] = [
  { value: "id_card", key: "docIdCard" },
  { value: "passport", key: "docPassport" },
];

const ERRORS: Record<string, Key> = {
  too_large: "docErrTooLarge",
  invalid_type: "docErrType",
  missing: "docErrType",
  too_many: "docErrTooMany",
  rejected: "idRejected",
};

/**
 * Dépôt d'une pièce d'identité (carte ou passeport), vérifiée à la main par l'équipe Sanad.
 * Solution de secours quand le registre national ne reconnaît pas le client ou ne répond pas.
 */
export function IdentityDocument({ user, open, onUploaded }: {
  user: User; open: boolean; onUploaded: (user: User) => void;
}) {
  const { t, lang } = useI18n();
  const [docs, setDocs] = useState<KycDocument[]>([]);
  const [kind, setKind] = useState<KycDocument["kind"]>("id_card");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ tone: "green" | "red"; key: Key } | null>(null);

  useEffect(() => {
    api<KycDocument[]>("me/documents").then(setDocs).catch(() => setDocs([]));
  }, []);

  async function send(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setStatus(null);
    const form = new FormData();
    form.append("kind", kind);
    form.append("file", file);
    try {
      const doc = await apiUpload<KycDocument>("me/documents", form);
      setDocs((list) => [doc, ...list]);
      setFile(null);
      setStatus({ tone: "green", key: "docSent" });
      onUploaded(await api<User>("me"));
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "";
      setStatus({ tone: "red", key: ERRORS[code] ?? "error" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="doc-upload" open={open || docs.length > 0}>
      <summary>{t("docTitle")}</summary>
      <div className="stack" style={{ gap: 12, paddingTop: 8 }}>
        {docs.length > 0 && (
          <ul className="stack" style={{ gap: 6, listStyle: "none", padding: 0, margin: 0 }} aria-label={t("docList")}>
            {docs.map((d) => (
              <li key={d.id} className="between small">
                <span>{t(d.kind === "passport" ? "docPassport" : "docIdCard")} · {date(d.uploaded_at, lang)}</span>
                <span className={`pill ${d.status === "accepted" ? "" : d.status === "rejected" ? "bad" : "warn"}`}>
                  {t(`docStatus_${d.status}` as Key)}
                </span>
              </li>
            ))}
          </ul>
        )}
        {user.kyc_status === "pending" && <p className="small ink2" style={{ margin: 0 }}>{t("kycPendingPay")}</p>}

        <form className="stack" style={{ gap: 12 }} onSubmit={send}>
          <p className="small ink2" style={{ margin: 0 }}>{t("docIntro")}</p>
          <fieldset className="field" style={{ border: "none", padding: 0, margin: 0 }}>
            <legend style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>{t("docKind")}</legend>
            <div className="segmented" style={{ gridTemplateColumns: "1fr 1fr" }} role="radiogroup">
              {KINDS.map((k) => (
                <button key={k.value} type="button" role="radio" aria-checked={kind === k.value} className="radio"
                  style={{ justifyContent: "center", minHeight: 48 }} onClick={() => setKind(k.value)}>
                  {t(k.key)}
                </button>
              ))}
            </div>
          </fieldset>
          <div className="field">
            <label htmlFor="doc-file">{t("docFile")}</label>
            <input id="doc-file" className="input" type="file" accept="image/jpeg,image/png,application/pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)} aria-describedby="doc-hint" />
            <span id="doc-hint" className="small muted">{t("docFileHint")} {t("docPrivacy")}</span>
          </div>
          <button className="btn outline block" disabled={!file || busy}>
            {busy ? <span className="spinner sm" aria-hidden="true" /> : <Icon name="file" size={20} strokeWidth={2} />}
            {busy ? t("docSending") : t("docSend")}
          </button>
          <div aria-live="polite">
            {status && (
              <p className={`banner ${status.tone}`} role={status.tone === "red" ? "alert" : "status"} style={{ margin: 0 }}>
                {t(status.key)}
              </p>
            )}
          </div>
        </form>
      </div>
    </details>
  );
}
