"""Petits éléments d'affichage du back-office : pastilles de statut, montants."""
from django.utils.html import format_html

TONES = {
    # Polices
    "draft": "quiet", "paid": "warn", "active": "ok", "refused": "bad", "cancelled": "quiet", "expired": "quiet",
    # Paiements et remboursements
    "pending": "warn", "succeeded": "ok", "failed": "bad", "refunded": "quiet", "requested": "warn", "done": "ok",
    # Entreprises, KYC, attestations
    "verified": "ok", "rejected": "bad", "none": "quiet", "valid": "ok", "revoked": "bad", "accepted": "ok",
    # Sinistres
    "submitted": "warn", "sent": "warn", "in_review": "warn", "closed": "quiet",
}


def pill(value: str, label, tone: str | None = None):
    return format_html('<span class="sn-pill sn-{}">{}</span>', tone or TONES.get(value, "quiet"), label)


def status_pill(obj, field: str = "status"):
    return pill(getattr(obj, field), getattr(obj, f"get_{field}_display")())


def mru(amount) -> str:
    if amount is None:
        return "—"
    return f"{int(amount):,}".replace(",", " ") + " MRU"


def yes_no(flag: bool, yes, no):
    return pill("ok" if flag else "quiet", yes if flag else no, "ok" if flag else "quiet")
