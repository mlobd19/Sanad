"""Connexions qui expirent (un jeton par appareil, révocables) et application d'authentification du back-office."""
import io
import re
import time
from datetime import timedelta

import pyotp
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import AuthToken, TotpDevice, User
from apps.accounts.tokens import digest, issue_token
from apps.audit.models import AuditEvent

from .conftest import login

pytestmark = pytest.mark.django_db


def client_with(key: str) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {key}")
    return client


def age(key: str, **delta):
    """Fait vieillir le jeton (sa date d'expiration recule d'autant)."""
    token = AuthToken.objects.get(digest=digest(key))
    AuthToken.objects.filter(pk=token.pk).update(expires_at=token.expires_at - timedelta(**delta))


# --- Expiration ----------------------------------------------------------------------------------

def test_customer_token_lasts_30_days(demo):
    key = login(APIClient(), "+22236000101")["token"]
    age(key, days=29, hours=23)
    assert client_with(key).get("/api/me").status_code == 200
    age(key, hours=2)  # au-delà de 30 jours
    resp = client_with(key).get("/api/me")
    assert resp.status_code == 401  # l'app renvoie alors vers /connexion
    assert not AuthToken.objects.filter(digest=digest(key)).exists()


def test_pro_token_lasts_8_hours(demo):
    agent = User.objects.get(email="agent@mar.test")
    key = issue_token(agent)
    token = AuthToken.objects.get(digest=digest(key))
    assert timedelta(hours=7, minutes=59) < token.expires_at - token.created_at <= timedelta(hours=8)
    age(key, hours=8, minutes=1)
    assert client_with(key).get("/api/insurer/me").status_code == 401


def test_token_is_never_stored_in_clear(demo):
    key = login(APIClient(), "+22236000102")["token"]
    assert not AuthToken.objects.filter(digest=key).exists()
    assert AuthToken.objects.filter(digest=digest(key)).count() == 1


# --- Un jeton par appareil, déconnexion ----------------------------------------------------------------

def test_one_token_per_device(demo):
    phone_a = login(APIClient(), "+22236000103")["token"]
    phone_b = login(APIClient(), "+22236000103")["token"]
    assert phone_a != phone_b
    # Le second appareil saisit le code du compte après le SMS : le premier reste connecté.
    assert client_with(phone_a).get("/api/me").status_code == 200
    assert client_with(phone_b).get("/api/me").status_code == 200


def test_logout_deletes_the_token_on_the_server(demo):
    key = login(APIClient(), "+22236000104")["token"]
    other = login(APIClient(), "+22236000104", pin=None)["token"]  # code SMS validé, code PIN pas encore choisi
    assert client_with(key).post("/api/auth/logout").status_code == 204
    assert client_with(key).get("/api/me").status_code == 401  # même copié, il ne vaut plus rien
    assert client_with(other).get("/api/auth/pin").status_code == 200  # l'autre appareil reste connecté


def test_logout_other_devices(demo):
    current = login(APIClient(), "+22236000105")["token"]
    others = [login(APIClient(), "+22236000105", pin=None)["token"] for _ in range(2)]
    resp = client_with(current).post("/api/auth/logout-others")
    assert resp.status_code == 200 and resp.data["closed"] == 2
    assert all(client_with(k).get("/api/auth/pin").status_code == 401 for k in others)
    assert client_with(current).get("/api/me").status_code == 200


def test_revoked_token_is_refused(demo):
    key = login(APIClient(), "+22236000106")["token"]
    AuthToken.objects.filter(digest=digest(key)).delete()  # ex. « Fermer » au back-office
    assert client_with(key).get("/api/me").status_code == 401


def test_password_change_closes_every_session(demo):
    agent = User.objects.get(email="agent@mar.test")
    keys = [issue_token(agent) for _ in range(2)]
    agent.set_password("Nouveau-Mot-De-Passe-2026")
    agent.save()
    assert not AuthToken.objects.filter(user=agent).exists()
    assert all(client_with(k).get("/api/insurer/me").status_code == 401 for k in keys)


def test_purge_removes_only_expired_tokens(demo):
    fresh = login(APIClient(), "+22236000107")["token"]
    old = login(APIClient(), "+22236000108")["token"]
    age(old, days=31)
    out = io.StringIO()
    call_command("purge_expired_tokens", stdout=out)
    assert "1 connexion" in out.getvalue()
    assert AuthToken.objects.filter(digest=digest(fresh)).exists()
    assert not AuthToken.objects.filter(digest=digest(old)).exists()


# --- Back-office : application d'authentification (TOTP) -----------------------------------------------

@pytest.fixture
def staff(db):
    return User.objects.create_user("+22230000000", password="Equipe-Sanad-2026", role=User.Role.STAFF,
                                    is_staff=True, is_superuser=True, full_name="Équipe Sanad")


def password_step(client=None) -> Client:
    client = client or Client()
    resp = client.post("/admin/login/?next=/admin/", {"username": "+22230000000", "password": "Equipe-Sanad-2026"})
    assert resp.status_code == 302 and resp.url == "/admin/login/totp/"
    return client


def code_for(user: User, offset_steps: int = 0) -> str:
    return pyotp.TOTP(TotpDevice.objects.get(user=user).secret).at(time.time() + offset_steps * 30)


def test_first_access_shows_qr_code_then_confirms_with_a_code(staff):
    client = password_step()
    assert client.get("/admin/").status_code == 302  # mot de passe seul : pas de session
    page = client.get("/admin/login/totp/").content.decode()
    assert 'src="data:image/png;base64,' in page  # QR code à scanner
    secret = TotpDevice.objects.get(user=staff).secret
    assert secret in page and TotpDevice.objects.get(user=staff).confirmed_at is None

    resp = client.post("/admin/login/totp/", {"code": code_for(staff)})
    assert resp.status_code == 302 and resp.url == "/admin/"
    assert client.get("/admin/").status_code == 200
    assert TotpDevice.objects.get(user=staff).confirmed_at is not None
    assert AuditEvent.objects.filter(action="totp.enrolled").exists()
    assert AuditEvent.objects.filter(action="user.login", data__method="password+totp").exists()

    # Connexion suivante : plus de QR code, seulement le code.
    again = password_step(Client()).get("/admin/login/totp/").content.decode()
    assert "data:image/png" not in again and secret not in again


def test_wrong_totp_code_is_refused(staff):
    client = password_step()
    client.get("/admin/login/totp/")
    good = code_for(staff)
    wrong = f"{(int(good) + 1) % 1_000_000:06d}"
    resp = client.post("/admin/login/totp/", {"code": wrong})
    assert resp.status_code == 200 and b"errornote" in resp.content
    assert client.get("/admin/").status_code == 302


def test_totp_brute_force_sends_back_to_password(staff):
    client = password_step()
    client.get("/admin/login/totp/")
    for _ in range(5):
        client.post("/admin/login/totp/", {"code": "000000" if code_for(staff) != "000000" else "111111"})
    assert client.get("/admin/login/totp/").url == "/admin/login/"  # tout est à recommencer


def test_totp_code_cannot_be_replayed(staff):
    client = password_step()
    client.get("/admin/login/totp/")
    code = code_for(staff)
    assert client.post("/admin/login/totp/", {"code": code}).status_code == 302
    other = password_step(Client())
    resp = other.post("/admin/login/totp/", {"code": code})  # même code, autre navigateur
    assert resp.status_code == 200 and b"errornote" in resp.content


def test_sms_second_factor_ignored_outside_debug(staff, settings):
    settings.DEBUG, settings.BACKOFFICE_2FA = False, "sms"
    password_step()  # redirige quand même vers l'application d'authentification


def test_reset_totp_command_is_audited(staff):
    client = password_step()
    client.get("/admin/login/totp/")
    client.post("/admin/login/totp/", {"code": code_for(staff)})
    old_secret = TotpDevice.objects.get(user=staff).secret

    out = io.StringIO()
    call_command("reset_totp", "+222 30 00 00 00", stdout=out)
    assert not TotpDevice.objects.filter(user=staff).exists()
    assert AuditEvent.objects.filter(action="totp.reset", object_id=str(staff.pk)).exists()
    page = password_step(Client()).get("/admin/login/totp/").content.decode()
    assert "data:image/png" in page and old_secret not in page  # nouveau QR code, nouveau secret

    with pytest.raises(CommandError):
        call_command("reset_totp", "+22299999999")


def test_backoffice_session_lasts_8_hours_and_ends_with_the_browser(staff, settings):
    assert settings.SESSION_COOKIE_AGE == 8 * 3600
    assert settings.SESSION_EXPIRE_AT_BROWSER_CLOSE is True
    client = password_step()
    client.get("/admin/login/totp/")
    resp = client.post("/admin/login/totp/", {"code": code_for(staff)})
    cookie = resp.cookies["sessionid"]
    assert not cookie["expires"] and not cookie["max-age"]  # cookie de session : fermé avec le navigateur
    assert client.session.get_expiry_age() <= 8 * 3600
    assert re.fullmatch(r"\w+", cookie.value)
