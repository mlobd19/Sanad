"""Second facteur du back-office : application d'authentification (TOTP, RFC 6238).

Premier accès : un secret est créé, l'équipier le scanne (QR code) dans son application, puis
confirme avec un premier code. Ensuite : mot de passe + code à 6 chiffres de l'application.
Un code ne sert qu'une fois (dernier pas mémorisé). Perte du téléphone : manage.py reset_totp.
"""
import base64
import hmac
import io
import time

import pyotp
import qrcode
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.models import record

from .models import TotpDevice, User

ISSUER = "Sanad back-office"
WINDOW = 1  # un pas de 30 s avant ou après : tolère un léger décalage d'horloge du téléphone


def second_factor() -> str:
    """« totp » partout ; « sms » ou « off » seulement en DEBUG (refusés en production par config/production.py)."""
    if settings.DEBUG and settings.BACKOFFICE_2FA in ("sms", "off"):
        return settings.BACKOFFICE_2FA
    return "totp"


def is_enrolled(user: User) -> bool:
    return TotpDevice.objects.filter(user=user, confirmed_at__isnull=False).exists()


def start_enrollment(user: User) -> TotpDevice:
    """Secret à scanner : créé au premier accès, gardé tant qu'il n'est pas confirmé."""
    device, _ = TotpDevice.objects.get_or_create(user=user, defaults={"secret": pyotp.random_base32()})
    return device


def provisioning_uri(device: TotpDevice) -> str:
    return pyotp.TOTP(device.secret).provisioning_uri(name=device.user.phone, issuer_name=ISSUER)


def qr_data_uri(text: str) -> str:
    image = qrcode.make(text, box_size=6, border=2)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


@transaction.atomic
def verify(user: User, code: str) -> bool:
    """Vrai si le code est juste et n'a jamais servi ; confirme l'inscription au premier code juste."""
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    device = TotpDevice.objects.select_for_update().filter(user=user).first()
    if device is None or len(code) != 6:
        return False
    totp = pyotp.TOTP(device.secret)
    current = int(time.time()) // totp.interval
    for step in range(current - WINDOW, current + WINDOW + 1):
        if step > device.last_step and hmac.compare_digest(totp.generate_otp(step), code):
            device.last_step = step
            first = device.confirmed_at is None
            if first:
                device.confirmed_at = timezone.now()
            device.save(update_fields=["last_step", "confirmed_at"])
            if first:
                record("totp.enrolled", user, actor=user)
            return True
    return False


def reset(user: User, via: str) -> bool:
    """Téléphone perdu : supprime l'application enregistrée ; un nouveau QR code sera proposé à la connexion."""
    deleted = TotpDevice.objects.filter(user=user).delete()[0] > 0
    record("totp.reset", user, via=via, had_device=deleted)
    return deleted
