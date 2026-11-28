"""Code PIN à 4 chiffres des particuliers (les comptes pro et le back-office ne sont pas concernés).

- Première connexion sur un appareil : code SMS, puis (fenêtre de SETUP_WINDOW) :
  - compte sans code : choix du code ;
  - compte qui a déjà un code : ce code est demandé (mêmes règles : 3 essais) ; le bon code connecte
    l'appareil sans fermer les autres. « Code oublié ? » : nouveau code, tous les autres appareils
    fermés et SMS au client (« pin_reset »).
- Ouvertures suivantes : le jeton de l'appareil (accounts/tokens.py) ne donne accès à rien sans le
  code PIN ; le bon code ouvre une session courte, fermée après PIN_SESSION_IDLE minutes d'inactivité.
- MAX_FAILURES codes faux de suite : connexion de l'appareil fermée, retour au code SMS (journal « pin.blocked »).
- Le code est vérifié côté serveur et haché par le hacheur de mots de passe de Django : jamais en clair,
  jamais dans les journaux.
"""
import re
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from apps.audit.models import record
from apps.notifications.service import notify

from .models import AuthToken, User

PIN_LENGTH = 4
MAX_FAILURES = 3
SETUP_WINDOW = timedelta(minutes=10)  # après le code SMS, pour choisir et confirmer le code PIN
ACTIVITY_PRECISION = timedelta(minutes=1)  # évite une écriture en base à chaque requête
OLDEST_YEAR = 1940  # années refusées : de 1940 à l'année en cours (souvent une date de naissance)


class PinError(Exception):
    """Refus lisible par l'app : `code` machine (traduit), message français, essais restants éventuels."""

    def __init__(self, code: str, message: str, attempts_left: int | None = None):
        super().__init__(message)
        self.code = code
        self.attempts_left = attempts_left


def applies(user: User) -> bool:
    return user.role == User.Role.CUSTOMER


def idle() -> timedelta:
    return timedelta(minutes=settings.PIN_SESSION_IDLE)


def too_simple(pin: str, phone: str = "") -> bool:
    """Codes trop faciles à deviner : 0000, 1234, 4321, 1212, une année de naissance, la fin du numéro."""
    digits = [int(c) for c in pin]
    steps = {b - a for a, b in zip(digits, digits[1:])}
    if len(set(digits)) == 1 or steps in ({1}, {-1}):
        return True
    if pin[:2] == pin[2:]:
        return True
    if OLDEST_YEAR <= int(pin) <= timezone.localdate().year:
        return True
    return bool(phone) and re.sub(r"\D", "", phone)[-PIN_LENGTH:] == pin


def check_new_pin(user: User, pin: str) -> str:
    pin = str(pin or "")
    if not re.fullmatch(rf"\d{{{PIN_LENGTH}}}", pin):
        raise PinError("pin_invalid", "Le code compte 4 chiffres.")
    if too_simple(pin, user.phone):
        raise PinError("pin_weak", "Code trop simple, choisissez-en un autre.")
    return pin


def state(token: AuthToken, now=None) -> str:
    """État de l'appareil :
    - « setup » : code SMS validé, compte sans code PIN : il le choisit ;
    - « verify » : code SMS validé, compte qui a déjà un code : il le saisit (ou en choisit un nouveau) ;
    - « open » : session ouverte ; « locked » : code PIN à saisir ;
    - « closed » : pas de code PIN et plus de fenêtre de choix (reconnexion par SMS)."""
    now = now or timezone.now()
    if token.pin_setup_until and token.pin_setup_until > now:
        return "verify" if token.user.pin else "setup"
    if not token.user.pin:
        return "closed"
    if token.pin_open_at and now - token.pin_open_at < idle():
        return "open"
    return "locked"


def touch(token: AuthToken) -> None:
    """Activité dans une session ouverte : le délai d'inactivité repart."""
    now = timezone.now()
    if token.pin_open_at and now - token.pin_open_at > ACTIVITY_PRECISION:
        AuthToken.objects.filter(pk=token.pk).update(pin_open_at=now)
        token.pin_open_at = now


def _open(token: AuthToken) -> None:
    token.pin_setup_until = None
    token.pin_open_at = timezone.now()
    token.pin_failures = 0
    token.save(update_fields=["pin_setup_until", "pin_open_at", "pin_failures"])


def _store(token: AuthToken, pin: str, action: str) -> int:
    """Enregistre le nouveau code du compte et ferme ses autres appareils (comme un nouveau mot de passe)."""
    user = token.user
    user.pin = make_password(pin)
    user.pin_changed_at = timezone.now()
    user.save(update_fields=["pin", "pin_changed_at"])
    closed = AuthToken.objects.filter(user=user).exclude(pk=token.pk).delete()[0]
    _open(token)
    record(action, user, actor=user, closed=closed)
    if action == "pin.reset":
        # Prévenir le client : si ce n'est pas lui, quelqu'un a reçu ses SMS (carte SIM volée…).
        transaction.on_commit(lambda: notify("sms", user.phone, "pin_reset", {}, language=user.language))
    return closed


def _check(token: AuthToken, pin: str) -> None:
    """Vérifie le code du compte ; un code faux compte pour l'appareil, le 3e de suite ferme sa connexion."""
    if check_password(str(pin or ""), token.user.pin):
        return
    # Erreurs levées après la transaction : sinon la fermeture de la connexion serait annulée.
    with transaction.atomic():
        current = AuthToken.objects.select_for_update().filter(pk=token.pk).first()
        failures = current.pin_failures + 1 if current is not None else MAX_FAILURES
        if current is not None and failures >= MAX_FAILURES:
            record("pin.blocked", token.user, actor=token.user, device=token.user_agent[:80])
            current.delete()
        elif current is not None:
            current.pin_failures = failures
            current.save(update_fields=["pin_failures"])
    if current is None:  # fermée entre-temps
        raise PinError("pin_blocked", "Session fermée. Reconnectez-vous par SMS.")
    if failures >= MAX_FAILURES:
        raise PinError("pin_blocked", "Trois codes incorrects : reconnectez-vous par SMS.")
    token.pin_failures = failures
    raise PinError("pin_wrong", "Code incorrect.", attempts_left=MAX_FAILURES - failures)


def set_after_sms(token: AuthToken, pin: str) -> int:
    """Choix du code PIN juste après le code SMS : premier code du compte (« pin.set »), ou « Code oublié ? »
    (« pin.reset ») : nouveau code, tous les autres appareils fermés, SMS au client."""
    current = state(token)
    if current not in ("setup", "verify"):
        raise PinError("pin_setup_expired", "Délai dépassé. Reconnectez-vous par SMS.")
    pin = check_new_pin(token.user, pin)
    return _store(token, pin, "pin.reset" if current == "verify" else "pin.set")


def unlock(token: AuthToken, pin: str) -> None:
    """Ouverture de l'app (ou nouvel appareil, après le SMS, si le compte a déjà un code) : le bon code ouvre
    une session courte, sans fermer les autres appareils."""
    current = state(token)
    if current == "setup":
        raise PinError("pin_setup", "Choisissez d'abord votre code.")
    if current == "closed":
        raise PinError("pin_blocked", "Session fermée. Reconnectez-vous par SMS.")
    _check(token, pin)
    _open(token)


def change(token: AuthToken, old: str, new: str) -> int:
    """Profil : ancien code puis nouveau code (confirmé dans l'app) ; ferme les autres appareils."""
    _check(token, old)
    return _store(token, check_new_pin(token.user, new), "pin.changed")
