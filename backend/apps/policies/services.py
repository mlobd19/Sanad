"""Cycle de vie des devis et des polices.

brouillon → payée → active  (validation assureur, ou automatique si l'assureur est en API)
                  ↘ refusée → remboursement
active → résiliée (révoque l'attestation) | expirée

Mêmes transitions pour l'auto et le voyage (préparation du voyage et devis : travel.py).
"""
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.accounts.storage import detect_document_type
from apps.audit.models import record
from apps.catalog.models import DEFAULT_DURATION, DURATIONS, Product
from apps.notifications.service import notify

from . import travel
from .models import Claim, ClaimPhoto, Commission, InsuredAsset, Policy, Quote, Traveler, VehicleUsage, normalize_plate

QUOTE_VALIDITY = timedelta(hours=48)
REQUIRED_VEHICLE_ATTRIBUTES = {"fiscal_power", "usage"}
USAGE_ERROR = "Usage inconnu : personnel ou commercial."


def check_vehicle_usage(usage) -> str:
    """Usage du véhicule : « personal » ou « commercial » (il n'y a plus de catégorie « taxi »)."""
    if usage not in VehicleUsage.values:
        raise ValidationError(USAGE_ERROR, code="invalid_usage")
    return usage


def parse_duration(value) -> int:
    """Durée demandée (3, 6 ou 12 mois) ; 12 mois si rien n'est précisé."""
    if value in (None, ""):
        return DEFAULT_DURATION
    try:
        months = int(value)
    except (TypeError, ValueError):
        months = None
    if months not in DURATIONS:
        raise ValidationError("Durée possible : 3, 6 ou 12 mois.")
    return months


def compute_quotes(customer, asset: InsuredAsset, branch=Product.Branch.AUTO, months: int = DEFAULT_DURATION) -> list[Quote]:
    if asset.owner_id != customer.pk or asset.company_id:
        raise PermissionDenied("Ce bien n'appartient pas à ce client.")
    return build_quotes(customer, asset, branch, months)


def build_quotes(customer, asset: InsuredAsset, branch=Product.Branch.AUTO, months: int = DEFAULT_DURATION) -> list[Quote]:
    """Devis auto de tous les assureurs actifs pour ce véhicule et cette durée (droits vérifiés par l'appelant).

    Voyage : travel.build_travel_quotes."""
    if asset.kind != InsuredAsset.Kind.VEHICLE:
        raise ValidationError("Devis auto : choisissez un véhicule.")
    months = parse_duration(months)
    missing = REQUIRED_VEHICLE_ATTRIBUTES - set(asset.attributes)
    if asset.kind == InsuredAsset.Kind.VEHICLE and missing:
        raise ValidationError(f"Attributs manquants : {', '.join(sorted(missing))}.")
    if asset.kind == InsuredAsset.Kind.VEHICLE:
        check_vehicle_usage(asset.attributes.get("usage"))
    products = Product.objects.filter(branch=branch, is_active=True, insurer__is_active=True).prefetch_related(
        "factors"
    ).select_related("insurer")
    expires = timezone.now() + QUOTE_VALIDITY
    quotes = [
        Quote(
            customer=customer,
            asset=asset,
            product=p,
            premium=p.price(asset.attributes, months),
            duration_months=months,
            tariff_version=p.tariff_version,
            attributes_snapshot=dict(asset.attributes),
            expires_at=expires,
        )
        for p in products
    ]
    created = Quote.objects.bulk_create(quotes)
    return sorted(created, key=lambda q: q.premium)


# --- Lecture de la carte grise ------------------------------------------------------

SCAN_MAX_UPLOAD = 15 * 1024 * 1024  # photo brute d'un téléphone récent


def scan_registration_card(user, upload) -> dict:
    """Pré-remplissage du formulaire véhicule depuis une photo de carte grise.

    La photo n'est jamais enregistrée : seuls les champs lus sont renvoyés, et le
    client les vérifie avant de valider. Lève registration_scan.ScanUnavailable ou
    ScanFailed si la lecture automatique n'a pas abouti.
    """
    from . import registration_scan

    if upload is None:
        raise ValidationError("Ajoutez une photo de la carte grise.", code="missing")
    if upload.size > SCAN_MAX_UPLOAD:
        raise ValidationError("Photo trop lourde (15 Mo maximum).", code="too_large")
    try:
        jpeg = registration_scan.prepare_image(upload.read())
    except ValueError:
        raise ValidationError("Photo illisible : utilisez une image JPEG ou PNG.", code="unreadable") from None
    data = registration_scan.read_card(jpeg)
    if not data.get("is_registration_card"):
        raise ValidationError("Ce document ne ressemble pas à une carte grise.", code="not_card")
    plate = normalize_plate(str(data.get("plate") or ""))[:40]
    make = " ".join(" ".join(str(data.get(k) or "") for k in ("make", "model")).split())[:80]
    try:
        power = int(data.get("fiscal_power") or 0)
    except (TypeError, ValueError):
        power = 0
    result = {"reference": plate, "make": make, "fiscal_power": power if 1 <= power <= 60 else None}
    record("vehicle.registration_scanned", user, actor=user, found=sorted(k for k, v in result.items() if v))
    return result


def _has_overlapping_cover(asset, starts_on, ends_on, exclude=None):
    """Auto : même immatriculation déjà couverte. Voyage : un voyageur (NNI) déjà couvert (travel.py)."""
    if asset.kind == InsuredAsset.Kind.TRIP:
        return bool(travel.covered_travelers(asset.trip, exclude=exclude))
    qs = Policy.objects.filter(
        asset__kind=InsuredAsset.Kind.VEHICLE,
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
    today = timezone.localdate()
    if quote.asset.kind == InsuredAsset.Kind.TRIP:
        # Voyage : couvert du départ au retour ; voyageurs et dates revérifiés.
        trip = quote.asset.trip
        travel.check_quote_matches_trip(quote, trip)
        travel.check_dates(trip.departure_on, trip.return_on, today)
        starts_on, ends_on = trip.departure_on, trip.return_on
        if _has_overlapping_cover(quote.asset, starts_on, ends_on):
            raise ValidationError("Un voyageur est déjà couvert par un autre contrat voyage sur ces dates.",
                                  code="traveler_overlap")
    else:
        starts_on = starts_on or today
        if starts_on < today or starts_on > today + timedelta(days=60):
            raise ValidationError("La date d'effet doit être comprise entre aujourd'hui et J+60.")
        ends_on = Policy.compute_end(starts_on, quote.duration_months)
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
    record("policy.created", policy, actor=customer, premium=policy.premium, months=quote.duration_months,
           days=quote.attributes_snapshot.get("days"))
    return policy


OVERLAP_REFUSAL = "Véhicule déjà couvert sur cette période : paiement remboursé."
TRAVEL_OVERLAP_REFUSAL = "Voyageur déjà couvert sur ces dates : paiement remboursé."


def on_payment_confirmed(policy: Policy):
    """Appelé par le module paiements, dans sa transaction."""
    policy = Policy.objects.select_for_update().get(pk=policy.pk)
    if policy.status != Policy.Status.DRAFT:
        return policy
    policy.status = Policy.Status.PAID
    policy.save(update_fields=["status", "updated_at"])
    record("policy.paid", policy)
    # Un véhicule ne peut pas être couvert deux fois. Vérifié au devis, mais deux brouillons du même
    # véhicule peuvent être payés l'un après l'autre (ou un particulier et une flotte) : on revérifie ici.
    # Verrou sur toutes les fiches de cette immatriculation : deux confirmations simultanées passent
    # l'une après l'autre, et la seconde voit la première.
    if policy.is_travel:
        # Voyage : même règle par voyageur. Verrou sur les fiches de ces NNI (tous voyages confondus).
        nnis = list(policy.asset.trip.travelers.values_list("nni", flat=True))
        list(Traveler.objects.select_for_update().filter(nni__in=nnis))
        if _has_overlapping_cover(policy.asset, policy.starts_on, policy.ends_on, exclude=policy):
            return _refuse(policy, actor=None, reason=TRAVEL_OVERLAP_REFUSAL, refund_note="Voyageur déjà couvert",
                           template="policy_refused_overlap_travel")
    else:
        list(InsuredAsset.objects.select_for_update().filter(reference=policy.asset.reference))
        if _has_overlapping_cover(policy.asset, policy.starts_on, policy.ends_on, exclude=policy):
            return _refuse(policy, actor=None, reason=OVERLAP_REFUSAL, refund_note="Véhicule déjà couvert",
                           template="policy_refused_overlap")
    if policy.product.insurer.auto_validate:
        return _activate(policy, actor=None)
    return policy


def _check_agent(agent, policy):
    if agent.is_superuser or agent.role == agent.Role.STAFF:
        return
    if agent.role != agent.Role.INSURER_AGENT or agent.insurer_id != policy.product.insurer_id:
        raise PermissionDenied("Vous ne pouvez pas décider pour cet assureur.")


def _activate(policy: Policy, actor, insurer_reference: str = "") -> Policy:
    from apps.attestations.services import issue_attestation, issue_travel_attestations

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
    if policy.is_travel:
        issue_travel_attestations(policy)  # une par voyageur
        trip = policy.asset.trip
        context = {"destinations_fr": travel.country_names(trip.destinations, "fr"),
                   "destinations_ar": travel.country_names(trip.destinations, "ar"),
                   "start": f"{trip.departure_on:%d/%m}", "end": f"{trip.return_on:%d/%m}"}
        transaction.on_commit(lambda: notify("sms", policy.customer.phone, "attestation_issued_travel", context,
                                             language=policy.customer.language))
        return policy
    attestation = issue_attestation(policy)
    transaction.on_commit(
        lambda: notify(
            "sms",  # attestation envoyée par SMS (lien de vérification)
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
    policy = Policy.objects.select_for_update().get(pk=policy.pk)
    _check_agent(agent, policy)
    if policy.status != Policy.Status.PAID:
        raise ValidationError("Seule une police payée peut être refusée.")
    if not reason.strip():
        raise ValidationError("Le motif du refus est obligatoire.")
    return _refuse(policy, actor=agent, reason=reason.strip())


def _refuse(policy: Policy, actor, reason: str, refund_note: str = "Refus de l'assureur",
            template: str = "policy_refused") -> Policy:
    """Transition paid → refused, remboursement automatique, client prévenu."""
    from apps.payments.services import refund_policy

    policy.status = Policy.Status.REFUSED
    policy.decided_by = actor
    policy.decided_at = timezone.now()
    policy.refusal_reason = reason
    policy.save()
    record("policy.refused", policy, actor=actor, reason=policy.refusal_reason)
    refund_policy(policy, actor=actor, note=refund_note)
    transaction.on_commit(
        lambda: notify(
            "sms",
            policy.customer.phone,
            template,
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
    # Rappel de renouvellement : auto seulement (un voyage ne se renouvelle pas).
    return Policy.objects.filter(status=Policy.Status.ACTIVE, ends_on=today + timedelta(days=days),
                                 asset__kind=InsuredAsset.Kind.VEHICLE).select_related("customer", "asset")


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


def parse_branch(raw: str | None) -> str | None:
    """Filtre par produit : « auto », « travel » ou rien (tous)."""
    if not raw:
        return None
    if raw not in (Product.Branch.AUTO, Product.Branch.TRAVEL):
        raise ValidationError(f"Produit inconnu : {raw}.")
    return raw


def insurer_policies(agent, statuses: list[str] | None = None, branch: str | None = None):
    insurer = agent_insurer(agent)
    qs = Policy.objects.filter(product__insurer=insurer).select_related(
        "product__insurer", "asset__trip", "customer", "company"
    ).prefetch_related("attestations", "payments", "renewals", "order__payments", "asset__trip__travelers__attestations")
    if statuses:
        qs = qs.filter(status__in=statuses)
    if branch:
        qs = qs.filter(product__branch=branch)
    return qs


def insurer_policy(agent, policy_id: int) -> Policy:
    """Police de la compagnie de l'agent ; Policy.DoesNotExist pour toute autre compagnie."""
    return insurer_policies(agent).get(pk=policy_id)


def insurer_commissions(agent, branch: str | None = None) -> dict:
    """Relevés mensuels et détail des commissions de la compagnie de l'agent (filtre facultatif par produit)."""
    insurer = agent_insurer(agent)
    qs = Commission.objects.filter(insurer=insurer)
    if branch:
        qs = qs.filter(policy__product__branch=branch)
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


# --- Sinistres ------------------------------------------------------------------------
# Le client déclare ; l'assureur (portail) ou l'équipe Sanad (back-office) prend en charge
# puis clôt. Le client est prévenu à chaque étape.

CLAIM_MAX_PHOTOS = 6
CLAIM_MAX_PHOTO_BYTES = 8 * 1024 * 1024
CLAIM_MAX_DESCRIPTION = 2000


def _notify_claim(claim: Claim, template: str, **context):
    # Prévenir celui qui a déclaré (pour une flotte : le membre de l'entreprise, pas forcément le souscripteur).
    person = claim.declared_by if claim.declared_by and claim.declared_by.is_active else claim.policy.customer
    context = {"number": claim.number, "insurer": claim.policy.product.insurer.name, **context}
    transaction.on_commit(lambda: notify("sms", person.phone, template, context, language=person.language))


def may_declare_claim(user, policy: Policy) -> bool:
    """Contrat de particulier : son titulaire. Contrat de flotte : tout membre actif de l'entreprise titulaire."""
    if not user.is_active:
        return False
    if policy.company_id:
        membership = getattr(user, "membership", None) if user.role == user.Role.COMPANY_MEMBER else None
        return membership is not None and membership.company_id == policy.company_id
    return policy.customer_id == user.pk


def declare_claim(customer, policy: Policy, data: dict, photos: list) -> Claim:
    """Déclaration d'un sinistre survenu pendant la période couverte, avec photos ou constat (6 au plus).

    `customer` est le déclarant : le client particulier, ou un membre de l'entreprise pour un véhicule de flotte.
    """
    if not may_declare_claim(customer, policy):
        raise PermissionDenied("Ce contrat n'appartient pas à ce compte.")
    if policy.status not in (Policy.Status.ACTIVE, Policy.Status.EXPIRED):
        raise ValidationError("Un sinistre se déclare sur un contrat en cours ou échu.", code="policy_inactive")

    kind = str(data.get("kind") or "")
    if kind not in (Claim.TRAVEL_KINDS if policy.is_travel else Claim.AUTO_KINDS):
        raise ValidationError("Choisissez le type de sinistre.", code="invalid_kind")
    traveler = None
    if policy.is_travel and data.get("traveler"):
        traveler = policy.asset.trip.travelers.filter(pk=str(data["traveler"])).first() \
            if str(data["traveler"]).isdigit() else None
        if traveler is None:
            raise ValidationError("Choisissez le voyageur concerné.", code="invalid_traveler")
    try:
        occurred_on = date.fromisoformat(str(data.get("occurred_on") or ""))
    except ValueError:
        raise ValidationError("Indiquez la date du sinistre.", code="invalid_date") from None
    if occurred_on > timezone.localdate():
        raise ValidationError("La date du sinistre ne peut pas être dans le futur.", code="future_date")
    if not policy.starts_on <= occurred_on <= policy.ends_on:
        raise ValidationError("Cette date n'est pas couverte par le contrat.", code="outside_cover")
    place = " ".join(str(data.get("place") or "").split())[:200]
    description = str(data.get("description") or "").strip()
    if not place or not description:
        raise ValidationError("Indiquez le lieu et décrivez ce qui s'est passé.", code="missing_fields")
    if len(description) > CLAIM_MAX_DESCRIPTION:
        raise ValidationError("Description trop longue (2 000 caractères au plus).", code="too_long")

    if len(photos) > CLAIM_MAX_PHOTOS:
        raise ValidationError("6 photos au plus.", code="too_many_photos")
    checked = []
    for upload in photos:
        if upload.size > CLAIM_MAX_PHOTO_BYTES:
            raise ValidationError("Photo trop lourde (8 Mo maximum).", code="too_large")
        ext = detect_document_type(upload)
        if not ext:
            raise ValidationError("Formats acceptés : JPEG, PNG, PDF.", code="invalid_type")
        checked.append((upload, ext))

    with transaction.atomic():
        claim = Claim.objects.create(
            policy=policy, declared_by=customer, kind=kind, traveler=traveler, occurred_on=occurred_on, place=place,
            description=description, third_party_plate=" ".join(str(data.get("third_party_plate") or "").upper().split())[:40],
            injuries=bool(data.get("injuries")),
        )
        for i, (upload, ext) in enumerate(checked, start=1):
            upload.name = f"photo-{i}.{ext}"
            ClaimPhoto.objects.create(claim=claim, file=upload)
        record("claim.declared", claim, actor=customer, kind=kind, photos=len(checked))
        _notify_claim(claim, "claim_received")
    return claim


def parse_claim_statuses(raw: str | None) -> list[str]:
    statuses = [s.strip() for s in (raw or "").split(",") if s.strip()]
    unknown = set(statuses) - set(Claim.Status.values)
    if unknown:
        raise ValidationError(f"Statut inconnu : {', '.join(sorted(unknown))}.")
    return statuses


def insurer_claims(agent, statuses: list[str] | None = None):
    """Sinistres de la compagnie de l'agent, les plus récents d'abord."""
    insurer = agent_insurer(agent)
    qs = Claim.objects.filter(policy__product__insurer=insurer).select_related(
        "policy__product__insurer", "policy__asset", "policy__customer", "policy__company", "declared_by", "handled_by"
    ).prefetch_related("photos")
    return qs.filter(status__in=statuses) if statuses else qs


def insurer_claim(agent, claim_id: int) -> Claim:
    """Sinistre de la compagnie de l'agent ; Claim.DoesNotExist pour toute autre compagnie."""
    return insurer_claims(agent).get(pk=claim_id)


@transaction.atomic
def take_claim(claim: Claim, actor) -> Claim:
    """L'assureur (ou l'équipe Sanad) prend le dossier en charge."""
    claim = Claim.objects.select_for_update().select_related("policy__product__insurer", "policy__customer").get(pk=claim.pk)
    _check_agent(actor, claim.policy)
    if claim.status != Claim.Status.SUBMITTED:
        raise ValidationError("Ce sinistre est déjà pris en charge ou clos.")
    claim.status, claim.handled_by = Claim.Status.IN_REVIEW, actor
    claim.save(update_fields=["status", "handled_by", "updated_at"])
    record("claim.taken", claim, actor=actor)
    _notify_claim(claim, "claim_in_review")
    return claim


@transaction.atomic
def close_claim(claim: Claim, actor, note: str) -> Claim:
    """Clôture avec une note pour le client (issue, indemnisation, pièces manquantes…)."""
    claim = Claim.objects.select_for_update().select_related("policy__product__insurer", "policy__customer").get(pk=claim.pk)
    _check_agent(actor, claim.policy)
    if claim.status == Claim.Status.CLOSED:
        raise ValidationError("Ce sinistre est déjà clos.")
    note = " ".join(note.split())
    if not note:
        raise ValidationError("La note de clôture est obligatoire : elle est envoyée au client.")
    claim.status, claim.handled_by, claim.closing_note = Claim.Status.CLOSED, actor, note[:500]
    claim.save(update_fields=["status", "handled_by", "closing_note", "updated_at"])
    record("claim.closed", claim, actor=actor, note=claim.closing_note)
    _notify_claim(claim, "claim_closed", note=claim.closing_note)
    return claim
