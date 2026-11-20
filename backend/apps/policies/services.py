"""Cycle de vie des devis et des polices.

brouillon → payée → active  (validation assureur, ou automatique si l'assureur est en API)
                  ↘ refusée → remboursement
active → résiliée (révoque l'attestation) | expirée
"""
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.audit.models import record
from apps.catalog.models import Product
from apps.notifications.service import notify

from .models import Commission, InsuredAsset, Policy, Quote

QUOTE_VALIDITY = timedelta(hours=48)
REQUIRED_VEHICLE_ATTRIBUTES = {"fiscal_power", "usage"}


def compute_quotes(customer, asset: InsuredAsset, branch=Product.Branch.AUTO) -> list[Quote]:
    if asset.owner_id != customer.pk or asset.company_id:
        raise PermissionDenied("Ce bien n'appartient pas à ce client.")
    return build_quotes(customer, asset, branch)


def build_quotes(customer, asset: InsuredAsset, branch=Product.Branch.AUTO) -> list[Quote]:
    """Devis de tous les assureurs actifs pour ce bien (droits vérifiés par l'appelant)."""
    missing = REQUIRED_VEHICLE_ATTRIBUTES - set(asset.attributes)
    if asset.kind == InsuredAsset.Kind.VEHICLE and missing:
        raise ValidationError(f"Attributs manquants : {', '.join(sorted(missing))}.")
    products = Product.objects.filter(branch=branch, is_active=True, insurer__is_active=True).prefetch_related(
        "factors"
    ).select_related("insurer")
    expires = timezone.now() + QUOTE_VALIDITY
    quotes = [
        Quote(
            customer=customer,
            asset=asset,
            product=p,
            premium=p.price(asset.attributes),
            tariff_version=p.tariff_version,
            attributes_snapshot=dict(asset.attributes),
            expires_at=expires,
        )
        for p in products
    ]
    created = Quote.objects.bulk_create(quotes)
    return sorted(created, key=lambda q: q.premium)


def _has_overlapping_cover(asset, starts_on, ends_on, exclude=None):
    qs = Policy.objects.filter(
        asset__reference__iexact=asset.reference,
        status__in=[Policy.Status.PAID, Policy.Status.ACTIVE],
        starts_on__lte=ends_on,
        ends_on__gte=starts_on,
    )
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs.exists()


@transaction.atomic
def create_policy(customer, quote: Quote, starts_on: date | None = None, renewal_of: Policy | None = None,
                  company=None, order=None) -> Policy:
    if quote.customer_id != customer.pk:
        raise PermissionDenied("Ce devis n'appartient pas à ce client.")
    if quote.expires_at <= timezone.now():
        raise ValidationError("Ce devis a expiré. Relancez une comparaison.")
    if hasattr(quote, "policy"):
        raise ValidationError("Ce devis a déjà été utilisé.")
    if customer.kyc_status == customer.KycStatus.REJECTED:
        raise ValidationError("Votre identité n'a pas pu être vérifiée.")
    today = timezone.localdate()
    starts_on = starts_on or today
    if starts_on < today or starts_on > today + timedelta(days=60):
        raise ValidationError("La date d'effet doit être comprise entre aujourd'hui et J+60.")
    ends_on = Policy.compute_end(starts_on, quote.product.duration_months)
    if _has_overlapping_cover(quote.asset, starts_on, ends_on):
        raise ValidationError("Ce véhicule est déjà couvert sur cette période.")
    policy = Policy.objects.create(
        quote=quote,
        customer=customer,
        asset=quote.asset,
        product=quote.product,
        premium=quote.premium,
        starts_on=starts_on,
        ends_on=ends_on,
        renewal_of=renewal_of,
        company=company,
        order=order,
    )
    record("policy.created", policy, actor=customer, premium=policy.premium)
    return policy


def on_payment_confirmed(policy: Policy):
    """Appelé par le module paiements, dans sa transaction."""
    policy = Policy.objects.select_for_update().get(pk=policy.pk)
    if policy.status != Policy.Status.DRAFT:
        return policy
    policy.status = Policy.Status.PAID
    policy.save(update_fields=["status", "updated_at"])
    record("policy.paid", policy)
    if policy.product.insurer.auto_validate:
        return _activate(policy, actor=None)
    return policy


def _check_agent(agent, policy):
    if agent.is_superuser or agent.role == agent.Role.STAFF:
        return
    if agent.role != agent.Role.INSURER_AGENT or agent.insurer_id != policy.product.insurer_id:
        raise PermissionDenied("Vous ne pouvez pas décider pour cet assureur.")


def _activate(policy: Policy, actor, insurer_reference: str = "") -> Policy:
    from apps.attestations.services import issue_attestation

    policy.status = Policy.Status.ACTIVE
    policy.decided_by = actor
    policy.decided_at = timezone.now()
    if insurer_reference:
        policy.insurer_reference = insurer_reference
    policy.save()
    insurer = policy.product.insurer
    amount = int((Decimal(policy.premium) * insurer.commission_rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    Commission.objects.create(
        policy=policy,
        insurer=insurer,
        rate=insurer.commission_rate,
        amount=amount,
        period=timezone.localdate().strftime("%Y-%m"),
    )
    record("policy.activated", policy, actor=actor)
    attestation = issue_attestation(policy)
    transaction.on_commit(
        lambda: notify(
            "whatsapp",
            policy.customer.phone,
            "attestation_issued",
            {"number": attestation.number, "url": attestation.verify_url},
            language=policy.customer.language,
        )
    )
    return policy


@transaction.atomic
def validate_policy(policy: Policy, agent, insurer_reference: str = "") -> Policy:
    policy = Policy.objects.select_for_update().get(pk=policy.pk)
    _check_agent(agent, policy)
    if policy.status != Policy.Status.PAID:
        raise ValidationError("Seule une police payée peut être validée.")
    return _activate(policy, agent, insurer_reference)


@transaction.atomic
def refuse_policy(policy: Policy, agent, reason: str) -> Policy:
    from apps.payments.services import refund_policy

    policy = Policy.objects.select_for_update().get(pk=policy.pk)
    _check_agent(agent, policy)
    if policy.status != Policy.Status.PAID:
        raise ValidationError("Seule une police payée peut être refusée.")
    if not reason.strip():
        raise ValidationError("Le motif du refus est obligatoire.")
    policy.status = Policy.Status.REFUSED
    policy.decided_by = agent
    policy.decided_at = timezone.now()
    policy.refusal_reason = reason.strip()
    policy.save()
    record("policy.refused", policy, actor=agent, reason=policy.refusal_reason)
    refund_policy(policy, actor=agent)
    transaction.on_commit(
        lambda: notify(
            "whatsapp",
            policy.customer.phone,
            "policy_refused",
            {"amount": policy.premium},
            language=policy.customer.language,
        )
    )
    return policy


@transaction.atomic
def cancel_policy(policy: Policy, actor, reason: str) -> Policy:
    from apps.attestations.services import revoke_attestations

    policy = Policy.objects.select_for_update().get(pk=policy.pk)
    if not (actor.is_superuser or actor.role == actor.Role.STAFF):
        _check_agent(actor, policy)
    if policy.status != Policy.Status.ACTIVE:
        raise ValidationError("Seule une police active peut être résiliée.")
    policy.status = Policy.Status.CANCELLED
    policy.save(update_fields=["status", "updated_at"])
    revoke_attestations(policy, reason=reason, actor=actor)
    record("policy.cancelled", policy, actor=actor, reason=reason)
    return policy


def expire_policies(today: date | None = None) -> int:
    today = today or timezone.localdate()
    return Policy.objects.filter(status=Policy.Status.ACTIVE, ends_on__lt=today).update(status=Policy.Status.EXPIRED)


def policies_due_for_reminder(days: int, today: date | None = None):
    today = today or timezone.localdate()
    return Policy.objects.filter(status=Policy.Status.ACTIVE, ends_on=today + timedelta(days=days)).select_related(
        "customer", "asset"
    )


# --- Portail assureur -----------------------------------------------------------
# Toutes les lectures partent de la compagnie de l'agent : un agent ne voit jamais
# les polices ni les commissions d'une autre compagnie.

# Taux de commission provisoire (15 %) tant que les contrats de partenariat ne sont
# pas signés : les montants sont affichés comme indicatifs.
COMMISSION_RATES_INDICATIVE = True


def agent_insurer(agent):
    """Compagnie de l'agent ; refuse tout compte qui n'est pas agent d'une compagnie."""
    if agent.role != agent.Role.INSURER_AGENT or not agent.insurer_id:
        raise PermissionDenied("Réservé aux agents d'une compagnie d'assurance.")
    return agent.insurer


def parse_statuses(raw: str | None) -> list[str]:
    """« paid » ou « active,expired » → liste de statuts connus (ValidationError sinon)."""
    statuses = [s.strip() for s in (raw or "").split(",") if s.strip()]
    unknown = set(statuses) - set(Policy.Status.values)
    if unknown:
        raise ValidationError(f"Statut inconnu : {', '.join(sorted(unknown))}.")
    return statuses


def insurer_policies(agent, statuses: list[str] | None = None):
    insurer = agent_insurer(agent)
    qs = Policy.objects.filter(product__insurer=insurer).select_related(
        "product__insurer", "asset", "customer", "company"
    ).prefetch_related("attestations", "payments", "renewals", "order__payments")
    if statuses:
        qs = qs.filter(status__in=statuses)
    return qs


def insurer_policy(agent, policy_id: int) -> Policy:
    """Police de la compagnie de l'agent ; Policy.DoesNotExist pour toute autre compagnie."""
    return insurer_policies(agent).get(pk=policy_id)


def insurer_commissions(agent) -> dict:
    """Relevés mensuels et détail des commissions de la compagnie de l'agent."""
    insurer = agent_insurer(agent)
    qs = Commission.objects.filter(insurer=insurer)
    months = (
        qs.values("period")
        .annotate(
            policies=Count("id"),
            premiums=Sum("policy__premium"),
            total=Sum("amount"),
            paid=Sum("amount", filter=Q(is_paid=True), default=0),
        )
        .order_by("-period")
    )
    items = qs.select_related("policy__asset", "policy__product").order_by("-period", "-created_at")
    return {
        "indicative": COMMISSION_RATES_INDICATIVE,
        "months": [
            {"period": m["period"], "policies": m["policies"], "premiums": m["premiums"],
             "amount": m["total"], "paid": m["paid"], "due": m["total"] - m["paid"]}
            for m in months
        ],
        "items": items,
    }
