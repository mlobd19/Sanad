"""Espace entreprise : inscription, vérification, membres, flotte, devis groupés, commandes.

Toute lecture et toute écriture part de l'entreprise du membre connecté
(member_company) : une entreprise ne voit jamais les données d'une autre.
"""
import csv
import io
import zipfile
from datetime import date

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts import services as accounts
from apps.accounts.models import OtpCode, User, normalize_phone
from apps.accounts.storage import detect_document_type
from apps.audit.models import record
from apps.notifications.service import notify
from apps.policies import services as policy_services
from apps.policies.models import Claim, InsuredAsset, Order, Policy, Quote, normalize_plate

from .models import Company, CompanyDocument, Membership, normalize_identifier

SIGNUP_SALT = "sanad.company-signup"
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
# Deux usages seulement (personnel, commercial), en français ou en anglais dans l'import CSV.
USAGES = {"personal": "personal", "personnel": "personal", "commercial": "commercial"}
MAX_IMPORT_ROWS = 500


def member_company(user) -> tuple[Company, Membership]:
    membership = getattr(user, "membership", None) if user.role == User.Role.COMPANY_MEMBER else None
    if membership is None or not user.is_active:
        raise PermissionDenied("Réservé aux membres d'une entreprise.")
    return membership.company, membership


def _require_admin(user) -> Company:
    company, membership = member_company(user)
    if membership.role != Membership.Role.ADMIN:
        raise PermissionDenied("Réservé à l'administrateur de l'entreprise.")
    return company


# --- Inscription en ligne ------------------------------------------------------------------


def _abandoned(user: User) -> bool:
    """Inscription jamais confirmée par SMS : on peut la reprendre de zéro."""
    return not user.is_active and user.last_login is None and user.role == User.Role.COMPANY_MEMBER


def _drop_abandoned_signup(user: User):
    membership = getattr(user, "membership", None)
    company = membership.company if membership else None
    user.delete()
    if company and not company.memberships.exists():
        company.delete()


@transaction.atomic
def signup(*, legal_name: str, nif: str, rc_number: str, address: str, full_name: str, email: str, phone: str,
           password: str, language: str = "fr") -> tuple[str, str]:
    """1re étape : crée l'entreprise et son administrateur (inactif), envoie un code SMS."""
    email = (email or "").strip().lower()
    phone = normalize_phone(phone)
    nif = normalize_identifier(nif)
    if not (legal_name or "").strip() or not (full_name or "").strip() or not email:
        raise ValidationError("Raison sociale, nom de l'administrateur et email sont obligatoires.")

    existing = User.objects.filter(email=email).first()
    if existing and _abandoned(existing):
        _drop_abandoned_signup(existing)
    elif existing:
        raise ValidationError("Un compte existe déjà avec cet email.")
    company = Company.objects.filter(nif=nif).first()
    if company:
        admins = [m.user for m in company.memberships.select_related("user")]
        if admins and all(_abandoned(u) for u in admins):
            for u in admins:
                _drop_abandoned_signup(u)
        else:
            raise ValidationError("Une entreprise est déjà inscrite avec ce NIF.")

    company = Company(legal_name=legal_name.strip(), nif=nif, rc_number=rc_number, address=(address or "").strip())
    company.full_clean()
    user = User(phone=phone, email=email, full_name=full_name.strip(), role=User.Role.COMPANY_MEMBER,
                is_active=False, language=language if language in ("fr", "ar") else "fr")
    validate_password(password or "", user)
    company.save()
    user.set_password(password)
    user.save()
    Membership.objects.create(company=company, user=user, role=Membership.Role.ADMIN)
    accounts.send_code(phone, OtpCode.Purpose.SIGNUP)
    record("company.signup_started", company, actor=user)
    return signing.dumps({"u": user.pk}, salt=SIGNUP_SALT), accounts.mask_phone(phone)


def verify_signup(challenge: str, code: str) -> User:
    """2e étape : le code SMS confirme le numéro et active le compte administrateur."""
    try:
        data = signing.loads(challenge or "", salt=SIGNUP_SALT, max_age=settings.OTP_TTL_SECONDS)
    except signing.BadSignature:
        raise accounts.LoginError("Inscription expirée. Recommencez le formulaire.") from None
    user = User.objects.filter(pk=data.get("u"), role=User.Role.COMPANY_MEMBER, is_active=False).first()
    if user is None:
        raise accounts.LoginError("Inscription introuvable ou déjà confirmée.")
    try:
        accounts.check_code(user.phone, code, OtpCode.Purpose.SIGNUP)
    except accounts.OtpError as exc:
        raise accounts.LoginError(str(exc)) from None
    user.is_active = True
    user.last_login = timezone.now()
    user.save(update_fields=["is_active", "last_login"])
    record("company.signed_up", user.membership.company, actor=user)
    return user


# --- Pièces et vérification -----------------------------------------------------------------


def add_document(user, kind: str, file) -> CompanyDocument:
    company = _require_admin(user)
    if kind not in CompanyDocument.Kind.values:
        raise ValidationError("Type de pièce inconnu : NIF ou Registre du Commerce.")
    if file is None:
        raise ValidationError("Joignez le fichier.")
    if file.size > MAX_UPLOAD_BYTES:
        raise ValidationError("Fichier trop lourd (8 Mo maximum).")
    ext = detect_document_type(file)  # sur le contenu, pas sur le type annoncé par le navigateur
    if not ext:
        raise ValidationError("Formats acceptés : JPEG, PNG, PDF.")
    file.name = f"{kind}.{ext}"
    doc = CompanyDocument.objects.create(company=company, kind=kind, file=file, uploaded_by=user)
    if company.status == Company.Status.REJECTED:  # nouvelle pièce après un refus : on revérifie
        company.status, company.rejection_reason = Company.Status.PENDING, ""
        company.save(update_fields=["status", "rejection_reason"])
    record("company.document_uploaded", company, actor=user, kind=kind)
    return doc


def missing_documents(company: Company) -> list[str]:
    present = set(company.documents.values_list("kind", flat=True))
    return [k for k in CompanyDocument.Kind.values if k not in present]


def _notify_admins(company: Company, template: str, context: dict):
    for m in company.memberships.filter(role=Membership.Role.ADMIN, user__is_active=True).select_related("user"):
        notify("email", m.user.email, template, {"company": company.legal_name, **context},
               language=m.user.language)


@transaction.atomic
def verify_company(company: Company, staff) -> Company:
    if missing_documents(company):
        raise ValidationError("Pièces manquantes : NIF et Registre du Commerce sont obligatoires.")
    company.status, company.rejection_reason = Company.Status.VERIFIED, ""
    company.verified_by, company.verified_at = staff, timezone.now()
    company.save()
    record("company.verified", company, actor=staff)
    transaction.on_commit(lambda: _notify_admins(company, "company_verified", {}))
    return company


@transaction.atomic
def reject_company(company: Company, staff, reason: str) -> Company:
    if not (reason or "").strip():
        raise ValidationError("Le motif du refus est obligatoire.")
    company.status, company.rejection_reason = Company.Status.REJECTED, reason.strip()[:255]
    company.verified_by, company.verified_at = staff, timezone.now()
    company.save()
    record("company.rejected", company, actor=staff, reason=company.rejection_reason)
    transaction.on_commit(lambda: _notify_admins(company, "company_rejected", {"reason": company.rejection_reason}))
    return company


# --- Membres ------------------------------------------------------------------------------------


@transaction.atomic
def invite_member(admin, *, full_name: str, email: str, phone: str, role: str = Membership.Role.MANAGER) -> User:
    company = _require_admin(admin)
    email = (email or "").strip().lower()
    if not email or not (full_name or "").strip():
        raise ValidationError("Nom et email sont obligatoires.")
    if role not in Membership.Role.values:
        raise ValidationError("Rôle inconnu.")
    if User.objects.filter(email=email).exists():
        raise ValidationError("Un compte existe déjà avec cet email.")
    user = User.objects.create_user(phone, role=User.Role.COMPANY_MEMBER, email=email, full_name=full_name.strip())
    Membership.objects.create(company=company, user=user, role=role, invited_by=admin)
    accounts.send_password_email(user, "invite", actor=admin)
    record("company.member_invited", company, actor=admin, member=user.pk, role=role)
    return user


# --- Flotte -----------------------------------------------------------------------------------------


def fleet(user):
    company, _ = member_company(user)
    return company.assets.filter(kind=InsuredAsset.Kind.VEHICLE).prefetch_related(
        "policies__product__insurer").order_by("reference")


def add_vehicle(user, reference: str, attributes: dict) -> InsuredAsset:
    company, _ = member_company(user)
    plate = normalize_plate(reference)
    if not 4 <= len(plate) <= 20:
        raise ValidationError("Immatriculation manquante ou invalide.")
    try:
        power = int(str(attributes.get("fiscal_power", "")).strip())
    except ValueError:
        raise ValidationError("Puissance fiscale (CV) manquante ou invalide.") from None
    if not 1 <= power <= 60:
        raise ValidationError("Puissance fiscale entre 1 et 60 CV.")
    usage = USAGES.get(str(attributes.get("usage", "")).strip().lower())
    if usage is None:
        raise ValidationError("Usage inconnu : personnel ou commercial.")
    if company.assets.filter(kind=InsuredAsset.Kind.VEHICLE, reference__iexact=plate).exists():
        raise ValidationError(f"{plate} est déjà dans la flotte.")
    attrs = {"fiscal_power": power, "usage": usage}
    make = str(attributes.get("make", "")).strip()
    if make:
        attrs["make"] = make[:60]
    asset = InsuredAsset.objects.create(owner=user, company=company, reference=plate, attributes=attrs)
    record("company.vehicle_added", asset, actor=user)
    return asset


HEADERS = {
    "immatriculation": "reference", "plaque": "reference", "reference": "reference", "plate": "reference",
    "marque": "make", "make": "make", "modele": "make", "modèle": "make",
    "cv": "fiscal_power", "puissance": "fiscal_power", "fiscal_power": "fiscal_power",
    "usage": "usage",
}


def import_fleet(user, raw: bytes) -> dict:
    """CSV (séparateur ; ou ,) : immatriculation, marque, cv, usage. Les lignes valides sont ajoutées."""
    member_company(user)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    lines = text.splitlines()
    if not lines:
        raise ValidationError("Fichier vide.")
    delimiter = ";" if lines[0].count(";") >= lines[0].count(",") else ","
    reader = csv.reader(lines, delimiter=delimiter)
    header = [HEADERS.get(h.strip().lower()) for h in next(reader)]
    if "reference" not in header or "fiscal_power" not in header or "usage" not in header:
        raise ValidationError("En-tête attendu : immatriculation ; marque ; cv ; usage.")
    created, errors = [], []
    for number, row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(created) + len(errors) >= MAX_IMPORT_ROWS:
            errors.append({"line": number, "message": f"Au-delà de {MAX_IMPORT_ROWS} lignes : importez en plusieurs fois."})
            break
        values = {key: (row[i] if i < len(row) else "") for i, key in enumerate(header) if key}
        try:
            with transaction.atomic():
                asset = add_vehicle(user, values.get("reference", ""), values)
            created.append(asset.reference)
        except ValidationError as exc:
            errors.append({"line": number, "plate": values.get("reference", "").strip(), "message": exc.messages[0]})
    return {"created": created, "errors": errors}


# --- Devis groupés et commandes -----------------------------------------------------------------


def quote_selection(user, asset_ids: list[int], months: int = 12) -> list[dict]:
    """Offres de chaque compagnie pour toute la sélection : prix par véhicule et total."""
    company, _ = member_company(user)
    ids = {int(i) for i in asset_ids or []}
    assets = list(company.assets.filter(pk__in=ids, kind=InsuredAsset.Kind.VEHICLE))
    if not ids or len(assets) != len(ids):
        raise ValidationError("Sélectionnez des véhicules de votre flotte.")
    offers: dict[int, dict] = {}
    for asset in assets:
        for quote in policy_services.build_quotes(user, asset, months=months):
            product = quote.product
            offer = offers.setdefault(product.pk, {"product": product, "lines": []})
            offer["lines"].append({"asset_id": asset.pk, "plate": asset.reference, "quote_id": quote.pk,
                                   "premium": quote.premium})
    complete = [o for o in offers.values() if len(o["lines"]) == len(assets)]
    for offer in complete:
        offer["total"] = sum(line["premium"] for line in offer["lines"])
        offer["lines"].sort(key=lambda line: line["plate"])
    return sorted(complete, key=lambda o: o["total"])


@transaction.atomic
def create_order(user, quote_ids: list[int], starts_on: date | None = None) -> Order:
    company, _ = member_company(user)
    ids = {int(i) for i in quote_ids or []}
    quotes = list(Quote.objects.select_related("asset", "product").filter(
        pk__in=ids, customer=user, asset__company=company))
    if not ids or len(quotes) != len(ids):
        raise ValidationError("Devis introuvables : relancez la comparaison.")
    if len({q.asset_id for q in quotes}) != len(quotes):
        raise ValidationError("Un seul devis par véhicule.")
    if len({q.duration_months for q in quotes}) != 1:
        raise ValidationError("Une commande porte sur une seule durée.")
    order = Order.objects.create(company=company, created_by=user)
    for quote in sorted(quotes, key=lambda q: q.asset.reference):
        try:
            policy_services.create_policy(user, quote, starts_on=starts_on, company=company, order=order)
        except ValidationError as exc:
            if quote.asset.kind == InsuredAsset.Kind.TRIP:
                raise  # mission : un seul contrat, l'erreur garde son code (traduit par l'app)
            raise ValidationError(f"{quote.asset.reference} : {exc.messages[0]}") from exc
    record("order.created", order, actor=user, policies=len(quotes), total=order.total)
    return order


def company_order(user, order_id: int) -> Order:
    company, _ = member_company(user)
    return Order.objects.get(pk=order_id, company=company)


def pay_order(user, order: Order, provider: str, payer_phone: str = ""):
    from apps.payments.services import initiate_order_payment

    company, _ = member_company(user)
    if order.company_id != company.pk:
        raise PermissionDenied("Cette commande n'appartient pas à votre entreprise.")
    if not company.is_verified:
        raise ValidationError("Le paiement sera possible une fois votre entreprise vérifiée (NIF et RC).")
    return initiate_order_payment(user, order, provider, payer_phone)


# --- Contrats et attestations --------------------------------------------------------------------


def company_policies(user, statuses: list[str] | None = None):
    company, _ = member_company(user)
    qs = Policy.objects.filter(company=company).select_related("product__insurer", "asset__trip").prefetch_related(
        "attestations", "renewals", "asset__trip__travelers__attestations")
    if statuses:
        qs = qs.filter(status__in=statuses)
    return qs


def company_policy(user, policy_id: int) -> Policy:
    """Contrat de l'entreprise du membre ; Policy.DoesNotExist pour celui d'une autre entreprise."""
    return company_policies(user).get(pk=policy_id)


def company_claims(user):
    """Sinistres déclarés sur les véhicules de la flotte, les plus récents d'abord."""
    company, _ = member_company(user)
    return Claim.objects.filter(policy__company=company).select_related(
        "policy__asset", "policy__product__insurer", "declared_by").prefetch_related("photos")


def declare_fleet_claim(user, policy_id: int, data: dict, photos: list) -> Claim:
    """Un membre de l'entreprise déclare un sinistre sur un véhicule de la flotte (mêmes règles qu'un particulier)."""
    return policy_services.declare_claim(user, company_policy(user, policy_id), data, photos)


def attestations_zip(user) -> bytes:
    """Toutes les attestations valides de l'entreprise, en PDF, dans un ZIP."""
    from apps.attestations.models import Attestation
    from apps.attestations.services import attestation_pdf

    company, _ = member_company(user)
    attestations = Attestation.objects.select_related(
        "policy__customer", "policy__asset", "policy__product__insurer", "policy__company"
    ).filter(policy__company=company, policy__status=Policy.Status.ACTIVE, status=Attestation.Status.VALID)
    if not attestations.exists():
        raise ValidationError("Aucune attestation valide pour le moment.")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for att in attestations:
            archive.writestr(f"attestation-{att.number}-{att.policy.asset.reference}.pdf",
                             attestation_pdf(att, actor=user))
    return buffer.getvalue()
