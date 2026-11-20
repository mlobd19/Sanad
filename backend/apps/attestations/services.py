import io

import qrcode
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import record

from . import signing
from .models import Attestation, AttestationCounter


def _next_number() -> str:
    year = timezone.localdate().year
    counter, _ = AttestationCounter.objects.select_for_update().get_or_create(year=year)
    counter.last += 1
    counter.save(update_fields=["last"])
    return f"{settings.ATTESTATION_NUMBER_PREFIX}-{year}-{counter.last:06d}"


@transaction.atomic
def issue_attestation(policy) -> Attestation:
    number = _next_number()
    payload = {
        "v": 1,
        "n": number,
        "p": policy.asset.reference.upper(),
        "i": policy.product.insurer.slug,
        "g": policy.product.code,
        "f": policy.starts_on.isoformat(),
        "t": policy.ends_on.isoformat(),
        "k": signing.key_id(),
    }
    attestation = Attestation.objects.create(
        policy=policy, number=number, payload=payload, token=signing.sign(payload)
    )
    record("attestation.issued", attestation, number=number)
    return attestation


def revoke_attestations(policy, reason: str, actor=None):
    now = timezone.now()
    for att in policy.attestations.filter(status=Attestation.Status.VALID):
        att.status = Attestation.Status.REVOKED
        att.revoked_at = now
        att.revoked_reason = reason[:255]
        att.save(update_fields=["status", "revoked_at", "revoked_reason"])
        record("attestation.revoked", att, actor=actor, reason=reason)


def mask_name(full_name: str) -> str:
    parts = (full_name or "").split()
    if not parts:
        return "—"
    return " ".join(p[0].upper() + "***" for p in parts)


def check(token: str) -> dict:
    """Vérification complète : signature, puis statut en base (révocation, dates)."""
    try:
        payload = signing.verify(token)
    except signing.InvalidToken:
        return {"authentic": False, "status": "invalid", "message": "Attestation non authentique."}

    att = (
        Attestation.objects.select_related("policy__product__insurer", "policy__customer")
        .filter(token=token)
        .first()
    )
    if att is None:
        return {"authentic": True, "status": "unknown", "message": "Signature valide mais attestation inconnue."}

    today = timezone.localdate()
    policy = att.policy
    if att.status == Attestation.Status.REVOKED:
        status, message = "revoked", "Attestation révoquée."
    elif today < policy.starts_on:
        status, message = "not_yet_valid", "Attestation pas encore en vigueur."
    elif today > policy.ends_on:
        status, message = "expired", "Attestation expirée."
    else:
        status, message = "valid", "Attestation valide."

    return {
        "authentic": True,
        "status": status,
        "message": message,
        "number": payload["n"],
        "plate": payload["p"],
        "insurer": policy.product.insurer.name,
        "cover": policy.product.name,
        "valid_from": payload["f"],
        "valid_to": payload["t"],
        "holder": mask_name(policy.customer.full_name),
    }


def qr_png(attestation: Attestation) -> bytes:
    image = qrcode.make(attestation.verify_url, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# --- PDF ------------------------------------------------------------------------


class AttestationRevoked(ValidationError):
    pass


def attestation_for(user, attestation_id: int) -> Attestation:
    """Attestation visible par ce compte : son titulaire (client ou entreprise), ou un agent de la compagnie.

    Attestation.DoesNotExist pour tout autre compte (on ne révèle pas qu'elle existe).
    """
    qs = Attestation.objects.select_related(
        "policy__customer", "policy__asset", "policy__product__insurer"
    ).filter(pk=attestation_id)
    if user.role == user.Role.INSURER_AGENT and user.insurer_id:
        return qs.get(policy__product__insurer_id=user.insurer_id)
    if user.role == user.Role.COMPANY_MEMBER:
        membership = getattr(user, "membership", None)
        if membership is None:
            raise Attestation.DoesNotExist
        return qs.get(policy__company_id=membership.company_id)
    return qs.get(policy__customer=user, policy__company__isnull=True)


def attestation_pdf(attestation: Attestation, actor=None) -> bytes:
    """PDF A4 bilingue. Une attestation révoquée ne se télécharge plus."""
    from .pdf import render

    if attestation.status != Attestation.Status.VALID:
        raise AttestationRevoked("Cette attestation a été révoquée : elle ne peut plus être téléchargée.")
    record("attestation.pdf_downloaded", attestation, actor=actor)
    return render(attestation, specimen=settings.ATTESTATION_SPECIMEN)
