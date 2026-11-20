"""Connexion et comptes.

- Particuliers : numéro de téléphone + code SMS (le compte se crée au premier code).
- Comptes professionnels (agents assureurs, membres d'entreprise) : email + mot de
  passe, puis code SMS envoyé au téléphone du compte. Le même numéro peut porter un
  compte particulier : la connexion par SMS seul n'ouvre jamais que celui-ci.
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.authtoken.models import Token

from apps.audit.models import record
from apps.notifications.service import notify

from . import identity
from .models import IdentityCheck, OtpCode, User, normalize_phone

PRO_CHALLENGE_SALT = "sanad.pro-login"
BAD_CREDENTIALS = "Email ou mot de passe incorrect."


class OtpError(Exception):
    pass


class LoginError(Exception):
    pass


def _hash(phone: str, code: str) -> str:
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def send_code(phone: str, purpose: str) -> OtpCode:
    code = f"{secrets.randbelow(10**6):06d}"
    with transaction.atomic():
        OtpCode.objects.filter(phone=phone, purpose=purpose, used=False).update(used=True)
        otp = OtpCode.objects.create(
            phone=phone,
            purpose=purpose,
            code_hash=_hash(phone, code),
            expires_at=timezone.now() + timedelta(seconds=settings.OTP_TTL_SECONDS),
        )
    notify("sms", phone, "otp", {"code": code, "minutes": settings.OTP_TTL_SECONDS // 60})
    return otp


def check_code(phone: str, code: str, purpose: str) -> None:
    """Vérifie et consomme le code ; OtpError sinon."""
    # L'erreur est levée APRÈS la transaction : sinon le compteur de tentatives
    # serait annulé avec elle et les essais deviendraient illimités.
    error = None
    with transaction.atomic():
        otp = (
            OtpCode.objects.select_for_update()
            .filter(phone=phone, purpose=purpose, used=False, expires_at__gt=timezone.now())
            .first()
        )
        if otp is None:
            error = "Code expiré ou inexistant. Demandez un nouveau code."
        elif otp.attempts >= settings.OTP_MAX_ATTEMPTS:
            otp.used = True
            otp.save(update_fields=["used"])
            error = "Trop de tentatives. Demandez un nouveau code."
        else:
            otp.attempts += 1
            if not hmac.compare_digest(otp.code_hash, _hash(phone, (code or "").strip())):
                otp.save(update_fields=["attempts"])
                error = "Code incorrect."
            else:
                otp.used = True
                otp.save(update_fields=["attempts", "used"])
    if error:
        raise OtpError(error)


# --- Particuliers : téléphone + code SMS ----------------------------------------------


def request_otp(raw_phone: str) -> OtpCode:
    return send_code(normalize_phone(raw_phone), OtpCode.Purpose.CUSTOMER)


def verify_otp(raw_phone: str, code: str) -> tuple[User, bool]:
    """Vérifie le code et renvoie (compte particulier de ce numéro, créé)."""
    phone = normalize_phone(raw_phone)
    check_code(phone, code, OtpCode.Purpose.CUSTOMER)
    # Jamais un compte pro, même s'il partage ce numéro.
    user = User.objects.filter(phone=phone).exclude(role__in=User.PRO_ROLES).first()
    created = user is None
    if created:
        user = User.objects.create_user(phone)
    record("user.login", user, actor=user, created=created)
    return user, created


# --- Comptes professionnels : email + mot de passe + code SMS -----------------------------


def mask_phone(phone: str) -> str:
    """+22220000002 → +222 •• •• •• 02"""
    return f"{phone[:4]} •• •• •• {phone[-2:]}"


def pro_login(email: str, password: str) -> tuple[str, str]:
    """1re étape : vérifie email et mot de passe, envoie le code SMS.

    Renvoie (défi signé à présenter avec le code, téléphone masqué). LoginError sinon,
    avec le même message que l'email existe ou non.
    """
    email = (email or "").strip().lower()
    user = User.objects.filter(email=email, is_active=True, role__in=User.PRO_ROLES).first() if email else None
    if user is None:
        make_password(password)  # même durée de réponse qu'un compte existant
        raise LoginError(BAD_CREDENTIALS)

    now = timezone.now()
    if user.locked_until and user.locked_until > now:
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        raise LoginError(f"Trop de tentatives. Réessayez dans {minutes} minute(s).")

    if not user.check_password(password or ""):
        user.failed_logins += 1
        if user.failed_logins >= settings.PRO_LOGIN_MAX_FAILURES:
            user.failed_logins = 0
            user.locked_until = now + timedelta(minutes=settings.PRO_LOGIN_LOCK_MINUTES)
            record("user.locked", user, minutes=settings.PRO_LOGIN_LOCK_MINUTES)
        user.save(update_fields=["failed_logins", "locked_until"])
        record("user.login_failed", user, step="password")
        raise LoginError(BAD_CREDENTIALS)

    if user.failed_logins or user.locked_until:
        user.failed_logins, user.locked_until = 0, None
        user.save(update_fields=["failed_logins", "locked_until"])
    send_code(user.phone, OtpCode.Purpose.PRO)
    challenge = signing.dumps({"u": user.pk}, salt=PRO_CHALLENGE_SALT)
    return challenge, mask_phone(user.phone)


def pro_verify(challenge: str, code: str) -> User:
    """2e étape : code SMS reçu sur le téléphone du compte."""
    try:
        data = signing.loads(challenge or "", salt=PRO_CHALLENGE_SALT, max_age=settings.OTP_TTL_SECONDS)
    except signing.BadSignature:  # inclut SignatureExpired
        raise LoginError("Session de connexion expirée. Saisissez à nouveau email et mot de passe.") from None
    user = User.objects.filter(pk=data.get("u"), is_active=True, role__in=User.PRO_ROLES).first()
    if user is None:
        raise LoginError(BAD_CREDENTIALS)
    try:
        check_code(user.phone, code, OtpCode.Purpose.PRO)
    except OtpError as exc:
        raise LoginError(str(exc)) from None
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    record("user.login", user, actor=user, method="email+password+sms")
    return user


# --- Mot de passe : invitation et réinitialisation par email ------------------------------


def portal_path(user: User) -> str:
    return {User.Role.INSURER_AGENT: "/assureur", User.Role.COMPANY_MEMBER: "/entreprise"}.get(user.role, "")


def password_link(user: User) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{settings.PORTAL_BASE_URL}{portal_path(user)}/mot-de-passe?uid={uid}&token={token}"


def send_password_email(user: User, kind: str, actor=None) -> None:
    """kind = "invite" (nouveau compte) ou "reset" (mot de passe oublié)."""
    if not user.email:
        raise ValidationError("Ce compte n'a pas d'email.")
    membership = getattr(user, "membership", None)
    organisation = user.insurer.name if user.insurer_id else (membership.company.legal_name if membership else "")
    context = {
        "name": user.full_name or user.email,
        "link": password_link(user),
        "phone": mask_phone(user.phone),
        "role": organisation or user.get_role_display(),
    }
    notify("email", user.email, f"password_{kind}", context, language=user.language)
    record(f"user.password_{kind}_sent", user, actor=actor)


def forgot_password(email: str) -> None:
    """Toujours silencieux : on ne révèle pas si l'email correspond à un compte."""
    email = (email or "").strip().lower()
    user = User.objects.filter(email=email, is_active=True, role__in=User.PRO_ROLES).first() if email else None
    if user:
        send_password_email(user, "reset")


def reset_password(uidb64: str, token: str, password: str) -> User:
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64 or "")), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        user = None
    if user is None or not user.is_pro or not default_token_generator.check_token(user, token or ""):
        raise ValidationError("Ce lien n'est plus valable. Demandez-en un nouveau.")
    validate_password(password or "", user)
    user.set_password(password)
    user.failed_logins, user.locked_until = 0, None
    user.save(update_fields=["password", "failed_logins", "locked_until"])
    Token.objects.filter(user=user).delete()  # ferme les sessions ouvertes avec l'ancien mot de passe
    record("user.password_set", user, actor=user)
    return user


# --- Identité : profil et registre national -------------------------------------


def update_profile(user: User, data: dict) -> User:
    """Mise à jour du profil. Changer le nom ou le NNI d'une identité vérifiée relance la vérification."""
    identity_changed = any(
        key in data and str(data[key]).strip() != getattr(user, key) for key in ("full_name", "nni")
    )
    for key in ("full_name", "nni", "language"):
        if key in data:
            setattr(user, key, str(data[key]).strip())
    fields = ["full_name", "nni", "language"]
    if identity_changed and user.kyc_status == User.KycStatus.VERIFIED:
        user.kyc_status = User.KycStatus.NONE
        fields.append("kyc_status")
        record("kyc.reset", user, actor=user, reason="identité modifiée")
    user.save(update_fields=fields)
    return user


def identity_check_available() -> bool:
    try:
        return identity.get_identity_provider() is not None
    except identity.IdentityUnavailable:
        return False


def verify_identity(user: User) -> IdentityCheck:
    """Interroge le registre national avec le NNI et le nom du profil.

    Correspondance : identité vérifiée. Désaccord ou NNI inconnu : rien n'est refusé
    automatiquement (fautes de saisie, translittération arabe / français) ; le client
    corrige son profil ou dépose une pièce vérifiée à la main dans le back-office.
    Lève identity.IdentityUnavailable si le registre ne répond pas.
    """
    if user.kyc_status == User.KycStatus.VERIFIED:
        raise ValidationError("Votre identité est déjà vérifiée.", code="already_verified")
    if user.kyc_status == User.KycStatus.REJECTED:
        raise ValidationError("Votre identité a été refusée : contactez le support.", code="rejected")
    nni, full_name = user.nni.strip(), user.full_name.strip()
    if not full_name or not nni:
        raise ValidationError("Renseignez votre nom complet et votre NNI.", code="missing_fields")
    if not identity.NNI_PATTERN.match(nni):
        raise ValidationError("Le NNI compte 10 chiffres.", code="invalid_nni")

    provider = identity.get_identity_provider()
    if provider is None:
        raise identity.IdentityUnavailable("vérification automatique désactivée")
    try:
        result = provider.verify(nni, full_name)
    except identity.IdentityUnavailable:
        IdentityCheck.objects.create(user=user, provider=provider.name, nni=nni, full_name=full_name,
                                     outcome=IdentityCheck.Outcome.UNAVAILABLE)
        raise
    check = IdentityCheck.objects.create(user=user, provider=provider.name, nni=nni, full_name=full_name,
                                         outcome=result.outcome, reference=result.reference)
    if result.outcome == identity.Outcome.MATCH:
        user.kyc_status = User.KycStatus.VERIFIED
        user.save(update_fields=["kyc_status"])
        record("kyc.verified", user, actor=user, method=provider.name, reference=result.reference)
    else:
        record("kyc.registry_no_match", user, actor=user, method=provider.name, outcome=result.outcome,
               reference=result.reference)
    return check
