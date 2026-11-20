"""Connexion et comptes.

- Particuliers : numéro de téléphone + code SMS (le compte se crée au premier code).
- Comptes professionnels (agents assureurs) : email + mot de passe, puis code SMS
  envoyé au téléphone du compte. Ils ne peuvent jamais se connecter par SMS seul.
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

from .models import OtpCode, User, normalize_phone

PRO_CHALLENGE_SALT = "sanad.pro-login"
BAD_CREDENTIALS = "Email ou mot de passe incorrect."
PRO_PHONE_MESSAGE = (
    "Ce numéro est celui d'un compte professionnel : connectez-vous avec votre email "
    "sur votre espace (portail assureur)."
)


class OtpError(Exception):
    pass


class LoginError(Exception):
    pass


def _hash(phone: str, code: str) -> str:
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def _send_otp(phone: str) -> OtpCode:
    code = f"{secrets.randbelow(10**6):06d}"
    with transaction.atomic():
        OtpCode.objects.filter(phone=phone, used=False).update(used=True)
        otp = OtpCode.objects.create(
            phone=phone,
            code_hash=_hash(phone, code),
            expires_at=timezone.now() + timedelta(seconds=settings.OTP_TTL_SECONDS),
        )
    notify("sms", phone, "otp", {"code": code, "minutes": settings.OTP_TTL_SECONDS // 60})
    return otp


def _consume_otp(phone: str, code: str) -> None:
    """Vérifie et consomme le code ; OtpError sinon."""
    # L'erreur est levée APRÈS la transaction : sinon le compteur de tentatives
    # serait annulé avec elle et les essais deviendraient illimités.
    error = None
    with transaction.atomic():
        otp = (
            OtpCode.objects.select_for_update()
            .filter(phone=phone, used=False, expires_at__gt=timezone.now())
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


def _is_pro_phone(phone: str) -> bool:
    return User.objects.filter(phone=phone, role__in=User.PRO_ROLES).exists()


# --- Particuliers : téléphone + code SMS ----------------------------------------------


def request_otp(raw_phone: str) -> OtpCode:
    phone = normalize_phone(raw_phone)
    if _is_pro_phone(phone):
        raise ValidationError(PRO_PHONE_MESSAGE)
    return _send_otp(phone)


def verify_otp(raw_phone: str, code: str) -> tuple[User, bool]:
    """Vérifie le code et renvoie (utilisateur, créé)."""
    phone = normalize_phone(raw_phone)
    if _is_pro_phone(phone):
        raise ValidationError(PRO_PHONE_MESSAGE)
    _consume_otp(phone, code)
    user, created = User.objects.get_or_create(phone=phone)
    if created:
        user.set_unusable_password()
        user.save()
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
    _send_otp(user.phone)
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
        _consume_otp(user.phone, code)
    except OtpError as exc:
        raise LoginError(str(exc)) from None
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    record("user.login", user, actor=user, method="email+password+sms")
    return user


# --- Mot de passe : invitation et réinitialisation par email ------------------------------


def portal_path(user: User) -> str:
    return "/assureur" if user.role == User.Role.INSURER_AGENT else "/"


def password_link(user: User) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{settings.PORTAL_BASE_URL}{portal_path(user)}/mot-de-passe?uid={uid}&token={token}"


def send_password_email(user: User, kind: str, actor=None) -> None:
    """kind = "invite" (nouveau compte) ou "reset" (mot de passe oublié)."""
    if not user.email:
        raise ValidationError("Ce compte n'a pas d'email.")
    context = {
        "name": user.full_name or user.email,
        "link": password_link(user),
        "phone": mask_phone(user.phone),
        "role": user.insurer.name if user.insurer_id else user.get_role_display(),
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
