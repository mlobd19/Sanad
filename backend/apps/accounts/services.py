import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.models import record
from apps.notifications.service import notify

from .models import OtpCode, User, normalize_phone


class OtpError(Exception):
    pass


def _hash(phone: str, code: str) -> str:
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def request_otp(raw_phone: str) -> OtpCode:
    phone = normalize_phone(raw_phone)
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


def verify_otp(raw_phone: str, code: str) -> tuple[User, bool]:
    """Vérifie le code et renvoie (utilisateur, créé)."""
    phone = normalize_phone(raw_phone)
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
                user, created = User.objects.get_or_create(phone=phone)
                if created:
                    user.set_unusable_password()
                    user.save()
    if error:
        raise OtpError(error)
    record("user.login", user, actor=user, created=created)
    return user, created
