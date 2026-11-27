"""Assurance voyage « Monde entier » : voyages, voyageurs et devis.

Le cycle de vie du contrat (brouillon → payé → actif…) reste celui de services.py ; ce module
prépare le voyage (destinations, dates, voyageurs) et calcule les devis. Règles :

- durée de 1 à 92 jours, départ et retour compris ; départ au plus tôt aujourd'hui, retour le jour
  du départ ou après ;
- chaque voyageur est identifié par son NNI (verify_eid) et son passeport. eID valide → nom officiel
  de l'ANRPTS, jamais modifiable ; pas d'eID valide (cas fréquent des enfants) → nom saisi tel qu'écrit
  sur le passeport, marqué « déclaré » ; NNI introuvable ou ANRPTS injoignable → voyageur refusé ;
- un même NNI ne peut pas avoir deux contrats voyage qui se chevauchent : vérifié au devis et
  revérifié à la confirmation du paiement (services.on_payment_confirmed).
"""
import json
import re
from datetime import date, timedelta
from pathlib import Path

from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts import identity
from apps.audit.models import record
from apps.catalog.models import TRAVEL_MAX_DAYS, Product

from .models import InsuredAsset, Policy, Quote, Traveler, Trip

COUNTRIES: dict[str, dict] = {
    c["code"]: c for c in json.loads((Path(__file__).parent / "countries.json").read_text(encoding="utf-8"))
}
MAX_DESTINATIONS = 10
MAX_TRAVELERS = {"customer": 9, "company": 50}
TRAVELER_CHECK_TTL = 30 * 60  # un NNI vérifié n'est pas réinterrogé pendant 30 min (ajout puis devis)
PASSPORT = re.compile(r"^[A-Z0-9]{6,15}$")
QUOTE_VALIDITY_HOURS = 48


def country_names(codes: list[str], lang: str = "fr") -> str:
    """« Espagne, France » (ou en arabe / anglais) pour l'affichage, le SMS et le PDF."""
    return ", ".join(COUNTRIES[c][lang] if c in COUNTRIES else c for c in codes)


# --- Voyage ------------------------------------------------------------------------------------


def normalize_destinations(raw) -> list[str]:
    codes = raw if isinstance(raw, list) else []
    result = []
    for code in codes:
        code = str(code).strip().upper()
        if code not in COUNTRIES:
            raise ValidationError("Destination inconnue.", code="invalid_destination")
        if code not in result:
            result.append(code)
    if not result:
        raise ValidationError("Choisissez au moins une destination.", code="missing_destination")
    if len(result) > MAX_DESTINATIONS:
        raise ValidationError("10 destinations au plus.", code="too_many_destinations")
    return result


def parse_day(value, code: str) -> date:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        raise ValidationError("Date invalide.", code=code) from None


def check_dates(departure_on: date, return_on: date, today: date | None = None) -> int:
    """Durée en jours (départ et retour compris) ; ValidationError si les dates ne conviennent pas."""
    today = today or timezone.localdate()
    if departure_on < today:
        raise ValidationError("Le départ est au plus tôt aujourd'hui.", code="departure_past")
    if return_on < departure_on:
        raise ValidationError("Le retour doit suivre le départ.", code="return_before_departure")
    days = (return_on - departure_on).days + 1
    if days > TRAVEL_MAX_DAYS:
        raise ValidationError("Un voyage dure 92 jours au plus.", code="too_long")
    return days


def owner_kind(company) -> str:
    return "company" if company is not None else "customer"


@transaction.atomic
def create_trip(user, destinations, departure_on, return_on, company=None) -> Trip:
    codes = normalize_destinations(destinations)
    departure = parse_day(departure_on, "invalid_departure")
    back = parse_day(return_on, "invalid_return")
    check_dates(departure, back)
    asset = InsuredAsset.objects.create(owner=user, company=company, kind=InsuredAsset.Kind.TRIP,
                                        reference="-".join(codes)[:40], attributes={})
    trip = Trip.objects.create(asset=asset, destinations=codes, departure_on=departure, return_on=back)
    record("trip.created", trip, actor=user, destinations=codes, days=trip.days, company=getattr(company, "pk", None))
    return trip


def trip_for(user, trip_id: int, company=None) -> Trip:
    """Voyage visible par ce compte : le sien (particulier) ou celui de son entreprise. Trip.DoesNotExist sinon."""
    qs = Trip.objects.select_related("asset").prefetch_related("travelers")
    if company is not None:
        return qs.get(pk=trip_id, asset__company=company)
    return qs.get(pk=trip_id, asset__owner=user, asset__company__isnull=True)


def is_locked(trip: Trip) -> bool:
    """Voyageurs figés dès qu'un contrat est payé (ou plus) : son prix et ses attestations en dépendent."""
    return trip.asset.policies.exclude(status=Policy.Status.DRAFT).exists()


# --- Voyageurs -----------------------------------------------------------------------------------


def check_traveler(user, nni: str) -> dict:
    """Identité d'un voyageur auprès de l'ANRPTS (eID), sans l'enregistrer.

    {"status": "verified", "full_name", "full_name_ar"} si l'eID est valide (nom officiel) ;
    {"status": "declared"} s'il n'a pas d'eID valide (nom à saisir tel que sur le passeport).
    NNI introuvable ou ANRPTS injoignable : ValidationError (mêmes messages que le profil).
    Résultat gardé 30 min par compte : l'ajout puis le devis n'interrogent l'ANRPTS qu'une fois.
    """
    from apps.accounts.models import IdentityCheck

    nni = str(nni or "").strip()
    if not identity.NNI_PATTERN.match(nni):
        raise ValidationError("Le NNI compte 10 chiffres.", code="invalid_nni")
    key = f"traveler-check:{user.pk}:{nni}"
    cached = cache.get(key)
    if cached:
        return cached
    result = identity.verify_eid(nni)
    IdentityCheck.objects.create(user=user, purpose=IdentityCheck.Purpose.TRAVELER, provider=result.provider,
                                 nni=nni, outcome=result.status, reference=result.reference)
    if result.status == identity.EidStatus.NOT_FOUND:
        raise ValidationError("Ce NNI est introuvable. Vérifiez les chiffres saisis et réessayez.", code="not_found")
    if result.status == identity.EidStatus.UNAVAILABLE:
        raise ValidationError("Service indisponible, réessayez dans quelques minutes.", code="unavailable")
    if result.status == identity.EidStatus.VALID:
        data = {"status": Traveler.Verification.VERIFIED, "full_name": result.full_name[:120],
                "full_name_ar": result.full_name_ar[:120], "reference": result.reference}
    else:  # pas d'eID valide
        data = {"status": Traveler.Verification.DECLARED, "full_name": "", "full_name_ar": "",
                "reference": result.reference}
    cache.set(key, data, TRAVELER_CHECK_TTL)
    return data


def normalize_passport(value) -> str:
    passport = re.sub(r"[\s\-.]+", "", str(value or "").upper())
    if not PASSPORT.match(passport):
        raise ValidationError("Numéro de passeport invalide (6 à 15 lettres ou chiffres).", code="invalid_passport")
    return passport


def check_birth_date(value) -> date:
    birth = parse_day(value, "invalid_birth_date")
    today = timezone.localdate()
    if birth > today or birth.year < today.year - 120:
        raise ValidationError("Date de naissance invalide.", code="invalid_birth_date")
    return birth


@transaction.atomic
def add_traveler(user, trip: Trip, *, nni, passport_number, birth_date, full_name="", company=None) -> Traveler:
    trip = Trip.objects.select_for_update().get(pk=trip.pk)
    if is_locked(trip):
        raise ValidationError("Ce voyage est déjà payé : ses voyageurs ne changent plus.", code="locked")
    if trip.travelers.count() >= MAX_TRAVELERS[owner_kind(company)]:
        raise ValidationError(f"{MAX_TRAVELERS[owner_kind(company)]} voyageurs au plus par contrat.",
                              code="too_many_travelers")
    nni = str(nni or "").strip()
    if trip.travelers.filter(nni=nni).exists():
        raise ValidationError("Ce voyageur est déjà ajouté.", code="already_added")
    passport = normalize_passport(passport_number)
    birth = check_birth_date(birth_date)
    checked = check_traveler(user, nni)
    if checked["status"] == Traveler.Verification.VERIFIED:
        # Nom officiel de l'ANRPTS : toute saisie est ignorée.
        name, name_ar = checked["full_name"], checked["full_name_ar"]
    else:
        name, name_ar = " ".join(str(full_name or "").split())[:120].upper(), ""
        if not name:
            raise ValidationError("Saisissez le nom tel qu'écrit sur le passeport.", code="name_required")
    traveler = Traveler.objects.create(trip=trip, nni=nni, full_name=name, full_name_ar=name_ar,
                                       passport_number=passport, birth_date=birth,
                                       verification=checked["status"], eid_reference=checked["reference"])
    covered = covered_travelers(trip)
    if covered:
        raise ValidationError(f"Un contrat voyage couvre déjà {covered[0]} sur ces dates.",
                              code="traveler_overlap")
    record("trip.traveler_added", trip, actor=user, verification=traveler.verification)
    return traveler


@transaction.atomic
def remove_traveler(user, trip: Trip, traveler_id: int):
    trip = Trip.objects.select_for_update().get(pk=trip.pk)
    if is_locked(trip):
        raise ValidationError("Ce voyage est déjà payé : ses voyageurs ne changent plus.", code="locked")
    deleted, _ = trip.travelers.filter(pk=traveler_id).delete()
    if not deleted:
        raise Traveler.DoesNotExist
    record("trip.traveler_removed", trip, actor=user)


# --- Chevauchement --------------------------------------------------------------------------------


def covered_travelers(trip: Trip, exclude: Policy | None = None) -> list[str]:
    """Voyageurs de ce voyage déjà couverts par un autre contrat voyage (payé ou actif) aux mêmes dates."""
    nnis = list(trip.travelers.values_list("nni", flat=True))
    if not nnis:
        return []
    policies = Policy.objects.filter(
        asset__kind=InsuredAsset.Kind.TRIP,
        status__in=[Policy.Status.PAID, Policy.Status.ACTIVE],
        starts_on__lte=trip.return_on,
        ends_on__gte=trip.departure_on,
    )
    if exclude is not None:
        policies = policies.exclude(pk=exclude.pk)
    taken = set(
        Traveler.objects.filter(trip__asset__policies__in=policies, nni__in=nnis).values_list("nni", flat=True)
    )
    return [t.full_name for t in trip.travelers.all() if t.nni in taken]


# --- Devis ------------------------------------------------------------------------------------------


def build_travel_quotes(user, trip: Trip) -> list[Quote]:
    """Un devis par offre voyage active (frais médicaux ≥ 30 000 €), prime = somme des voyageurs."""
    travelers = list(trip.travelers.all())
    if not travelers:
        raise ValidationError("Ajoutez au moins un voyageur.", code="no_travelers")
    days = check_dates(trip.departure_on, trip.return_on)
    covered = covered_travelers(trip)
    if covered:
        raise ValidationError(f"Un contrat voyage couvre déjà {covered[0]} sur ces dates.",
                              code="traveler_overlap")
    ages = [t.age_on(trip.departure_on) for t in travelers]
    products = Product.objects.filter(branch=Product.Branch.TRAVEL, is_active=True, insurer__is_active=True) \
        .select_related("insurer").prefetch_related("factors")
    expires = timezone.now() + timedelta(hours=QUOTE_VALIDITY_HOURS)
    quotes = []
    for product in products:
        if not product.meets_travel_minimum():
            continue  # jamais d'offre sous 30 000 € de frais médicaux (visa Schengen)
        premiums = product.travel_premiums(days, ages)
        quotes.append(Quote(
            customer=user, asset=trip.asset, product=product, premium=sum(premiums), duration_months=0,
            tariff_version=product.tariff_version, expires_at=expires,
            attributes_snapshot={
                "days": days, "destinations": trip.destinations,
                "travelers": [{"nni": t.nni, "age": age, "premium": premium}
                              for t, age, premium in zip(travelers, ages, premiums)],
            },
        ))
    created = Quote.objects.bulk_create(quotes)
    return sorted(created, key=lambda q: q.premium)


def check_quote_matches_trip(quote: Quote, trip: Trip):
    """Le devis porte sur les voyageurs actuels du voyage (sinon son prix ne vaut plus)."""
    quoted = [t["nni"] for t in quote.attributes_snapshot.get("travelers", [])]
    current = list(trip.travelers.values_list("nni", flat=True))
    if sorted(quoted) != sorted(current):
        raise ValidationError("Les voyageurs ont changé : relancez la comparaison.", code="quote_outdated")


def mask_passport(passport: str) -> str:
    return "•" * max(len(passport) - 3, 3) + passport[-3:] if passport else "—"
