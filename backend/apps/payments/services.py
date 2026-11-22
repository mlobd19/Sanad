import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import normalize_phone
from apps.audit.models import record
from apps.policies.models import Order, Policy

from .models import CallbackLog, Payment, Refund
from .providers import InvalidCallback, get_provider

logger = logging.getLogger("payments")


@transaction.atomic
def _payer(payer_phone: str) -> str:
    """Numéro qui paie (facultatif) : forme +222XXXXXXXX, ou ValidationError s'il est invalide."""
    return normalize_phone(payer_phone) if (payer_phone or "").strip() else ""


def initiate_payment(customer, policy: Policy, provider_name: str, payer_phone: str = "") -> tuple[Payment, str]:
    policy = Policy.objects.select_for_update().get(pk=policy.pk)
    if policy.customer_id != customer.pk:
        raise PermissionDenied("Cette police n'appartient pas à ce client.")
    if policy.status != Policy.Status.DRAFT:
        raise ValidationError("Cette police n'attend pas de paiement.")
    # Particuliers : identité vérifiée (registre national ou pièce validée) avant tout paiement.
    # Les commandes d'entreprise passent par initiate_order_payment (entreprise vérifiée NIF + RC).
    if customer.kyc_status != customer.KycStatus.VERIFIED:
        raise ValidationError("Vérifiez votre identité avant de payer.", code="kyc_required")
    _check_ceiling(policy.premium)
    try:
        provider = get_provider(provider_name)
    except KeyError as exc:
        raise ValidationError(str(exc)) from exc
    # Un seul paiement en attente par police : on abandonne les précédents.
    policy.payments.filter(status=Payment.Status.PENDING).update(
        status=Payment.Status.FAILED, failure_reason="Remplacé par une nouvelle tentative"
    )
    payment = Payment.objects.create(
        policy=policy, provider=provider.name, amount=policy.premium, payer_phone=_payer(payer_phone)
    )
    result = provider.initiate(payment)
    payment.external_ref = result.external_ref
    payment.save(update_fields=["external_ref"])
    record("payment.initiated", payment, actor=customer, provider=provider.name, amount=payment.amount)
    return payment, result.instructions


def _check_ceiling(amount: int):
    ceiling = settings.PAYMENT_MAX_AMOUNT
    if ceiling and amount > ceiling:
        raise ValidationError(
            f"Montant au-dessus du plafond d'une transaction mobile money ({ceiling} MRU) : "
            "souscrivez en plusieurs commandes."
        )


@transaction.atomic
def initiate_order_payment(member, order: Order, provider_name: str, payer_phone: str = "") -> tuple[Payment, str]:
    """Un seul paiement mobile money pour toutes les polices d'une commande."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    policies = list(order.policies.select_for_update())
    if not policies or any(p.status != Policy.Status.DRAFT for p in policies):
        raise ValidationError("Cette commande n'attend pas de paiement.")
    amount = sum(p.premium for p in policies)
    _check_ceiling(amount)
    try:
        provider = get_provider(provider_name)
    except KeyError as exc:
        raise ValidationError(str(exc)) from exc
    order.payments.filter(status=Payment.Status.PENDING).update(
        status=Payment.Status.FAILED, failure_reason="Remplacé par une nouvelle tentative"
    )
    payment = Payment.objects.create(order=order, provider=provider.name, amount=amount, payer_phone=_payer(payer_phone))
    result = provider.initiate(payment)
    payment.external_ref = result.external_ref
    payment.save(update_fields=["external_ref"])
    record("payment.initiated", payment, actor=member, provider=provider.name, amount=amount, order=order.pk)
    return payment, result.instructions


def handle_callback(provider_name: str, body: bytes, headers) -> str:
    """Traite un callback opérateur. Idempotent : rejouer le même callback ne change rien."""
    try:
        provider = get_provider(provider_name)
        data = provider.parse_callback(body, headers)
    except (KeyError, InvalidCallback) as exc:
        CallbackLog.objects.create(provider=provider_name, signature_ok=False, body=body.decode(errors="replace"),
                                   outcome=str(exc)[:80])
        raise
    with transaction.atomic():
        payment = (
            Payment.objects.select_for_update()
            .filter(provider=provider.name, external_ref=data.external_ref)
            .select_related("policy")
            .first()
        )
        outcome = _apply(payment, data)
        CallbackLog.objects.create(provider=provider.name, signature_ok=True, body=body.decode(errors="replace"),
                                   outcome=outcome)
    return outcome


def _apply(payment, data) -> str:
    if payment is None:
        return "unknown_reference"
    if payment.status in (Payment.Status.SUCCEEDED, Payment.Status.REFUNDED):
        return "already_processed"
    if not data.succeeded:
        payment.status = Payment.Status.FAILED
        payment.failure_reason = data.failure_reason[:255]
        payment.save(update_fields=["status", "failure_reason"])
        record("payment.failed", payment, reason=payment.failure_reason)
        return "failed"
    if data.amount != payment.amount:
        payment.status = Payment.Status.FAILED
        payment.failure_reason = f"Montant reçu {data.amount} ≠ attendu {payment.amount}"
        payment.save(update_fields=["status", "failure_reason"])
        record("payment.amount_mismatch", payment, received=data.amount, expected=payment.amount)
        logger.warning("Montant incohérent pour le paiement %s", payment.pk)
        return "amount_mismatch"

    payment.status = Payment.Status.SUCCEEDED
    payment.confirmed_at = timezone.now()
    payment.save(update_fields=["status", "confirmed_at"])
    record("payment.succeeded", payment, amount=payment.amount)

    from apps.policies.services import on_payment_confirmed

    if payment.order_id:
        policies = list(Policy.objects.select_for_update().filter(order_id=payment.order_id).order_by("pk"))
    else:
        policies = [Policy.objects.select_for_update().get(pk=payment.policy_id)]
    if all(p.status != Policy.Status.DRAFT for p in policies):
        # Double paiement (ex. deux tentatives confirmées) : on rembourse le second.
        _refund(payment, note="Double paiement")
        return "duplicate_refunded"
    for policy in policies:
        if policy.status == Policy.Status.DRAFT:
            on_payment_confirmed(policy)
    return "succeeded"


def _refund(payment: Payment, note: str, actor=None, amount: int | None = None, policy=None) -> Refund:
    """Rembourse tout le paiement, ou seulement `amount` (une ligne d'une commande)."""
    remaining = payment.amount - payment.refunded_amount
    amount = remaining if amount is None else min(amount, remaining)
    refund = Refund.objects.create(payment=payment, policy=policy, amount=amount, note=note)
    try:
        refund.external_ref = get_provider(payment.provider).refund(payment, amount)
        refund.status = Refund.Status.DONE
    except Exception as exc:  # l'équipe reprend à la main depuis le back-office
        refund.status = Refund.Status.FAILED
        refund.note = f"{note} · {exc}"[:255]
        logger.exception("Remboursement en échec pour le paiement %s", payment.pk)
    refund.save()
    if payment.refunded_amount >= payment.amount:
        payment.status = Payment.Status.REFUNDED
        payment.save(update_fields=["status"])
    record("payment.refunded", payment, actor=actor, refund_status=refund.status, note=note, amount=amount)
    return refund


def refund_policy(policy: Policy, actor=None, note: str = "Refus de l'assureur"):
    """Police refusée : la rembourse, seule, même si elle a été payée dans une commande."""
    for payment in policy.payments.select_for_update().filter(status=Payment.Status.SUCCEEDED):
        _refund(payment, note=note, actor=actor, policy=policy)
    if policy.order_id:
        for payment in Payment.objects.select_for_update().filter(order_id=policy.order_id,
                                                                   status=Payment.Status.SUCCEEDED):
            _refund(payment, note=f"{note} · police #{policy.pk}", actor=actor,
                    amount=policy.premium, policy=policy)
