"""Code PIN à 4 chiffres des particuliers : création, code faux, blocage après 3 erreurs, codes trop simples,
réinitialisation par SMS, session courte (PIN_SESSION_IDLE). Comptes pro et back-office inchangés."""
from datetime import timedelta

import pytest
from django.conf import settings as django_settings
from django.contrib.auth.hashers import check_password, identify_hasher
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import api as accounts_api
from apps.accounts import pin
from apps.accounts.models import AuthToken, User
from apps.accounts.tokens import digest, issue_token
from apps.audit.models import AuditEvent

from .conftest import TEST_PIN, login

PHONE = "+22236000301"


def device(key: str) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {key}")
    return client


def token_of(key: str) -> AuthToken:
    return AuthToken.objects.get(digest=digest(key))


def lock(key: str, minutes: int | None = None):
    """Fait vieillir la session du code PIN (par défaut : au-delà de PIN_SESSION_IDLE)."""
    minutes = django_settings.PIN_SESSION_IDLE + 1 if minutes is None else minutes
    AuthToken.objects.filter(digest=digest(key)).update(pin_open_at=timezone.now() - timedelta(minutes=minutes))


def unlock(client, code):
    return client.post("/api/auth/pin/unlock", {"pin": code}, format="json")


# --- Création ------------------------------------------------------------------------------------------

def test_first_login_asks_for_a_pin_before_anything(demo):
    data = login(APIClient(), PHONE, pin=None)
    assert data["pin"] == "setup"
    client = device(data["token"])
    resp = client.get("/api/me")
    assert resp.status_code == 403 and resp.data["code"] == "pin_setup"  # le jeton seul n'ouvre rien
    assert client.get("/api/auth/pin").data["state"] == "setup"

    assert client.post("/api/auth/pin/setup", {"pin": "1234"}, format="json").data["code"] == "pin_weak"
    assert client.post("/api/auth/pin/setup", {"pin": "12a4"}, format="json").data["code"] == "pin_invalid"
    resp = client.post("/api/auth/pin/setup", {"pin": TEST_PIN}, format="json")
    assert resp.status_code == 200 and resp.data["user"]["phone"] == PHONE
    assert client.get("/api/me").status_code == 200  # session ouverte tout de suite
    assert client.get("/api/auth/pin").data["state"] == "open"
    assert AuditEvent.objects.filter(action="pin.set").exists()


def test_pin_is_hashed_never_in_clear(demo):
    login(APIClient(), PHONE)
    user = User.objects.get(phone=PHONE, role=User.Role.CUSTOMER)
    assert user.pin != TEST_PIN and TEST_PIN not in user.pin
    identify_hasher(user.pin)  # format du hacheur de mots de passe de Django
    assert check_password(TEST_PIN, user.pin)
    assert all(TEST_PIN not in str(e.data) for e in AuditEvent.objects.all())  # jamais dans les journaux


def test_setup_window_closes_after_ten_minutes(demo):
    key = login(APIClient(), PHONE, pin=None)["token"]
    AuthToken.objects.filter(digest=digest(key)).update(pin_setup_until=timezone.now() - timedelta(seconds=1))
    assert device(key).get("/api/me").status_code == 401  # aucun code PIN : retour au SMS
    assert not AuthToken.objects.filter(digest=digest(key)).exists()


def test_setup_is_only_possible_right_after_sms(demo):
    key = login(APIClient(), PHONE)["token"]
    resp = device(key).post("/api/auth/pin/setup", {"pin": "1357"}, format="json")
    assert resp.status_code == 400 and resp.data["code"] == "pin_setup_expired"


# --- Ouvertures suivantes, code faux, blocage --------------------------------------------------------------

def test_next_opening_needs_the_pin_without_sms(demo, outbox):
    key = login(APIClient(), PHONE)["token"]
    lock(key)
    client = device(key)
    sms_before = len(outbox)
    resp = client.get("/api/me")
    assert resp.status_code == 403 and resp.data["code"] == "pin_required"
    status = client.get("/api/auth/pin").data
    assert status["state"] == "locked" and status["attempts_left"] == 3 and status["phone_end"] == "01"
    assert unlock(client, TEST_PIN).status_code == 200
    assert client.get("/api/me").status_code == 200
    assert len(outbox) == sms_before  # aucun SMS


def test_wrong_pin_counts_down_then_resets(demo):
    key = login(APIClient(), PHONE)["token"]
    lock(key)
    client = device(key)
    resp = unlock(client, "1357")
    assert resp.status_code == 400 and resp.data == {"detail": "Code incorrect.", "code": "pin_wrong", "attempts_left": 2}
    assert unlock(client, "1358").data["attempts_left"] == 1
    assert unlock(client, TEST_PIN).status_code == 200
    assert token_of(key).pin_failures == 0  # le bon code remet le compteur à zéro


def test_three_wrong_pins_close_the_device(demo):
    key = login(APIClient(), PHONE)["token"]
    lock(key)
    client = device(key)
    unlock(client, "1357")
    unlock(client, "1358")
    resp = unlock(client, "1359")
    assert resp.status_code == 401 and resp.data["code"] == "pin_blocked"
    assert not AuthToken.objects.filter(digest=digest(key)).exists()  # jeton révoqué
    assert AuditEvent.objects.filter(action="pin.blocked").count() == 1
    assert unlock(client, TEST_PIN).status_code == 401  # même le bon code : retour au code SMS
    assert client.get("/api/me").status_code == 401


def test_wrong_old_pin_in_change_counts_too(demo):
    key = login(APIClient(), PHONE)["token"]
    client = device(key)
    for _ in range(2):
        resp = client.post("/api/auth/pin/change", {"old": "1357", "new": "1470"}, format="json")
        assert resp.data["code"] == "pin_wrong"
    resp = client.post("/api/auth/pin/change", {"old": "1357", "new": "1470"}, format="json")
    assert resp.status_code == 401 and resp.data["code"] == "pin_blocked"


# --- Codes trop simples ----------------------------------------------------------------------------------

@pytest.mark.parametrize("code", [
    "0000", "1111", "9999",  # 4 chiffres identiques
    "1234", "0123", "6789", "4321", "9876", "3210",  # suites croissantes ou décroissantes
    "1212", "2020", "0101", "7878",  # répétitions de paires
    "1940", "1985", "2001",  # années de naissance probables
    "0001",  # 4 derniers chiffres du numéro (+222 36 00 00 01)
])
def test_too_simple_codes_are_refused(code):
    assert pin.too_simple(code, "+22236000001")


def test_current_year_and_phone_end_are_refused():
    assert pin.too_simple(str(timezone.localdate().year), "+22236000001")
    assert pin.too_simple("4567", "+22236004567")  # fin du numéro (aussi une suite)
    assert pin.too_simple("0937", "+22246000937")


@pytest.mark.parametrize("code", ["2580", "1357", "1939", "8642", "0937", "4090", str(timezone.localdate().year + 1)])
def test_reasonable_codes_are_accepted(code):
    assert not pin.too_simple(code, "+22236000001")


def test_refused_code_message(demo):
    key = login(APIClient(), PHONE, pin=None)["token"]
    resp = device(key).post("/api/auth/pin/setup", {"pin": "0301"}, format="json")  # fin du numéro du compte
    assert resp.status_code == 400 and resp.data == {"detail": "Code trop simple, choisissez-en un autre.", "code": "pin_weak"}


# --- Code oublié : réinitialisation par SMS, changement ---------------------------------------------------

def test_forgotten_pin_is_reset_by_sms_and_closes_other_devices(demo):
    old_device = login(APIClient(), PHONE)["token"]
    lock(old_device)
    # « Code oublié ? » : déconnexion de cet appareil, puis code SMS et nouveau code.
    assert device(old_device).post("/api/auth/logout").status_code == 204  # permise sans le code PIN
    other_device = login(APIClient(), PHONE, pin=None)["token"]
    third = login(APIClient(), PHONE, pin=None)["token"]
    new_device = device(login(APIClient(), PHONE, pin="1357")["token"])
    assert new_device.get("/api/me").status_code == 200
    assert device(other_device).get("/api/auth/pin").status_code == 401  # autres appareils fermés
    assert device(third).get("/api/auth/pin").status_code == 401
    user = User.objects.get(phone=PHONE, role=User.Role.CUSTOMER)
    assert check_password("1357", user.pin) and not check_password(TEST_PIN, user.pin)


def test_change_pin_closes_other_devices(demo):
    key = login(APIClient(), PHONE)["token"]
    waiting = login(APIClient(), PHONE, pin=None)["token"]  # appareil en cours de connexion
    client = device(key)
    resp = client.post("/api/auth/pin/change", {"old": TEST_PIN, "new": "1111"}, format="json")
    assert resp.data["code"] == "pin_weak"
    resp = client.post("/api/auth/pin/change", {"old": TEST_PIN, "new": "1357"}, format="json")
    assert resp.status_code == 200 and resp.data["closed"] == 1
    assert device(waiting).get("/api/auth/pin").status_code == 401
    assert AuditEvent.objects.filter(action="pin.changed").exists()
    lock(key)
    assert unlock(client, TEST_PIN).data["code"] == "pin_wrong"
    assert unlock(client, "1357").status_code == 200


def test_change_requires_an_open_session(demo):
    key = login(APIClient(), PHONE)["token"]
    lock(key)
    resp = device(key).post("/api/auth/pin/change", {"old": TEST_PIN, "new": "1357"}, format="json")
    assert resp.status_code == 403 and resp.data["code"] == "pin_required"


# --- Session courte ------------------------------------------------------------------------------------

def test_session_expires_after_idle_time(demo, settings):
    settings.PIN_SESSION_IDLE = 15
    key = login(APIClient(), PHONE)["token"]
    client = device(key)
    lock(key, minutes=14)
    assert client.get("/api/me").status_code == 200  # activité : le délai repart
    assert timezone.now() - token_of(key).pin_open_at < timedelta(seconds=5)
    lock(key, minutes=16)
    resp = client.get("/api/me")
    assert resp.status_code == 403 and resp.data["code"] == "pin_required"
    assert AuthToken.objects.filter(digest=digest(key)).exists()  # le jeton reste : seul le code est redemandé


def test_locked_device_is_a_visitor_on_public_endpoints(demo):
    key = login(APIClient(), PHONE)["token"]
    lock(key)
    assert device(key).post("/api/auth/otp/request", {"phone": PHONE}, format="json").status_code == 202


# --- Comptes pro et réglages -----------------------------------------------------------------------------

def test_pro_accounts_do_not_use_a_pin(demo):
    agent = User.objects.get(email="agent@mar.test")
    client = device(issue_token(agent))
    assert client.get("/api/insurer/me").status_code == 200  # sans code PIN
    assert client.get("/api/auth/pin").status_code == 403  # réservé aux particuliers
    assert token_of(issue_token(agent)).pin_setup_until is None


def test_pin_endpoints_have_their_own_throttle():
    for view in (accounts_api.PinSetupView, accounts_api.PinUnlockView, accounts_api.PinChangeView):
        assert view.throttle_scope == "pin"
    assert "pin" in django_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    assert pin.MAX_FAILURES == 3 and django_settings.PIN_SESSION_IDLE == 15
