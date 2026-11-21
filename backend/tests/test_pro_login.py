"""Connexion des comptes professionnels : email + mot de passe + code SMS."""
import re
from datetime import timedelta
from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.core import mail
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.accounts import services
from apps.accounts.models import User
from apps.notifications.backends import MemoryBackend

from .conftest import login

pytestmark = pytest.mark.django_db

PASSWORD = "Tamourt-2026-solide"
EMAIL = "agent@mar.test"


@pytest.fixture
def mar_agent(demo) -> User:
    agent = User.objects.get(phone="+22220000002")
    agent.set_password(PASSWORD)
    agent.save()
    return agent


def sms_code(phone: str) -> str:
    sms = [m for m in MemoryBackend.outbox if m["channel"] == "sms" and m["to"] == phone][-1]
    return re.search(r"\b(\d{6})\b", sms["body"]).group(1)


def sms_count(phone: str) -> int:
    return sum(1 for m in MemoryBackend.outbox if m["channel"] == "sms" and m["to"] == phone)


def step1(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/auth/pro/login", {"email": email, "password": password}, format="json")


def step2(client, challenge, code):
    return client.post("/api/auth/pro/verify", {"challenge": challenge, "code": code}, format="json")


# --- Parcours ---------------------------------------------------------------------------


def test_agent_logs_in_with_email_password_then_sms(mar_agent):
    client = APIClient()
    resp = step1(client, email="  Agent@MAR.test ")  # casse et espaces ignorés

    assert resp.status_code == 200
    assert resp.data["phone"] == "+222 •• •• •• 02"
    resp = step2(client, resp.data["challenge"], sms_code(mar_agent.phone))

    assert resp.status_code == 200
    assert resp.data["user"]["role"] == "insurer_agent"
    client.credentials(HTTP_AUTHORIZATION=f"Token {resp.data['token']}")
    assert client.get("/api/insurer/me").data["insurer"]["slug"] == "mar"


def test_wrong_password_sends_no_sms_and_same_message_as_unknown_email(mar_agent):
    client = APIClient()
    wrong = step1(client, password="mauvais-mot-de-passe")
    unknown = step1(client, email="personne@inconnu.test")

    assert wrong.status_code == unknown.status_code == 400
    assert wrong.data["detail"] == unknown.data["detail"] == "Email ou mot de passe incorrect."
    assert sms_count(mar_agent.phone) == 0


def test_wrong_sms_code_and_tampered_challenge_are_refused(mar_agent):
    client = APIClient()
    challenge = step1(client).data["challenge"]
    good = sms_code(mar_agent.phone)

    assert step2(client, challenge, "000000" if good != "000000" else "111111").status_code == 400
    assert step2(client, challenge[:-2] + "xx", good).status_code == 400
    assert step2(client, challenge, good).status_code == 200


def test_challenge_expires_with_the_sms_code(mar_agent, settings):
    client = APIClient()
    challenge = step1(client).data["challenge"]
    settings.OTP_TTL_SECONDS = -1  # le défi signé n'est plus accepté

    resp = step2(client, challenge, sms_code(mar_agent.phone))

    assert resp.status_code == 400
    assert "expirée" in resp.data["detail"]


def test_account_locked_after_five_wrong_passwords(mar_agent, settings):
    client = APIClient()
    for _ in range(settings.PRO_LOGIN_MAX_FAILURES):
        assert step1(client, password="mauvais-mot-de-passe").status_code == 400

    locked = step1(client)  # même le bon mot de passe est refusé pendant le blocage
    assert locked.status_code == 400
    assert "Trop de tentatives" in locked.data["detail"]
    assert sms_count(mar_agent.phone) == 0

    User.objects.filter(pk=mar_agent.pk).update(locked_until=timezone.now() - timedelta(seconds=1))
    assert step1(client).status_code == 200


def test_customer_account_cannot_use_pro_login(demo):
    client = APIClient()
    customer = User.objects.get(phone=login(client, "+22236000050")["user"]["phone"])
    customer.email = "client@exemple.test"
    customer.set_password(PASSWORD)
    customer.save()

    assert step1(APIClient(), email="client@exemple.test").status_code == 400


def test_sms_only_never_opens_the_agent_account(mar_agent):
    """Même numéro : le SMS seul ouvre (ou crée) le compte particulier, jamais le compte agent."""
    client = APIClient()
    step1(client)  # code « pro » envoyé au téléphone de l'agent
    pro_code = sms_code(mar_agent.phone)
    resp = client.post("/api/auth/otp/verify", {"phone": mar_agent.phone, "code": pro_code}, format="json")
    assert resp.status_code == 400  # un code « pro » ne vaut rien dans le parcours particulier

    data = login(client, mar_agent.phone)  # parcours particulier complet
    assert data["user"]["role"] == "customer"
    assert data["user"]["id"] != mar_agent.pk
    assert User.objects.filter(phone=mar_agent.phone).count() == 2
    assert client.get("/api/insurer/me").status_code == 403
    assert not Token.objects.filter(user=mar_agent).exists()


def test_personal_phone_stays_unique(demo):
    login(APIClient(), "+22236000060")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("+22236000060")


# --- Mot de passe ----------------------------------------------------------------------------


def link_from_last_email() -> tuple[str, str]:
    body = mail.outbox[-1].body
    uid = re.search(r"uid=([\w-]+)", body).group(1)
    token = re.search(r"token=([\w-]+)", body).group(1)
    return uid, token


def test_forgot_password_does_not_reveal_accounts(mar_agent):
    client = APIClient()
    unknown = client.post("/api/auth/pro/password/forgot", {"email": "personne@inconnu.test"}, format="json")
    known = client.post("/api/auth/pro/password/forgot", {"email": EMAIL}, format="json")

    assert unknown.status_code == known.status_code == 202
    assert unknown.data == known.data
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [EMAIL]
    assert "http://localhost:3000/assureur/mot-de-passe?uid=" in mail.outbox[0].body


def test_reset_password_flow(mar_agent):
    client = APIClient()
    old_session = Token.objects.create(user=mar_agent)
    client.post("/api/auth/pro/password/forgot", {"email": EMAIL}, format="json")
    uid, token = link_from_last_email()

    weak = client.post("/api/auth/pro/password/reset", {"uid": uid, "token": token, "password": "court"}, format="json")
    assert weak.status_code == 400

    new = "Nouakchott-Plage-2026"
    ok = client.post("/api/auth/pro/password/reset", {"uid": uid, "token": token, "password": new}, format="json")
    assert ok.status_code == 200
    assert not Token.objects.filter(key=old_session.key).exists()  # sessions précédentes fermées

    reused = client.post("/api/auth/pro/password/reset", {"uid": uid, "token": token, "password": "Autre-Mot-2026x"},
                         format="json")
    assert reused.status_code == 400  # lien à usage unique

    assert step1(client).status_code == 400  # ancien mot de passe
    assert step1(client, password=new).status_code == 200


def test_invitation_email_lets_a_new_agent_choose_a_password(demo):
    agent = User.objects.create_user("+22220000099", role=User.Role.INSURER_AGENT, insurer=demo["nasr"],
                                     email="nouvel.agent@nasr.test", full_name="Mariem")
    services.send_password_email(agent, "invite")

    assert "Choisissez votre mot de passe" in mail.outbox[-1].body
    assert "+222 •• •• •• 99" in mail.outbox[-1].body
    uid, token = link_from_last_email()
    resp = APIClient().post("/api/auth/pro/password/reset",
                            {"uid": uid, "token": token, "password": "Premier-Mot-2026"}, format="json")
    assert resp.status_code == 200
    assert step1(APIClient(), email="nouvel.agent@nasr.test", password="Premier-Mot-2026").status_code == 200


def test_reset_link_expires(mar_agent, settings):
    APIClient().post("/api/auth/pro/password/forgot", {"email": EMAIL}, format="json")
    uid, token = link_from_last_email()
    settings.PASSWORD_RESET_TIMEOUT = -1

    resp = APIClient().post("/api/auth/pro/password/reset", {"uid": uid, "token": token, "password": "Valable-2026-x"},
                            format="json")
    assert resp.status_code == 400
    assert "plus valable" in resp.data["detail"]


# --- Démo et migration ----------------------------------------------------------------------


DEMO_PASSWORD = "Mot-de-passe-demo-2026"


def test_seed_sets_demo_password_only_in_demo_mode(db, settings):
    settings.DEMO_MODE, settings.DEMO_PASSWORD = False, DEMO_PASSWORD
    settings.DEBUG = True  # DEBUG seul ne suffit pas : il faut DEMO_MODE
    call_command("seed_demo", verbosity=0)
    agent = User.objects.get(phone="+22220000002")
    assert agent.email == "agent@mar.test"
    assert not agent.has_usable_password()

    settings.DEMO_MODE = True
    call_command("seed_demo", verbosity=0)
    agent.refresh_from_db()
    assert agent.check_password(DEMO_PASSWORD)  # lu dans DEMO_PASSWORD, plus jamais en dur

    agent.set_password(PASSWORD)  # un mot de passe choisi n'est jamais écrasé
    agent.save()
    call_command("seed_demo", verbosity=0)
    agent.refresh_from_db()
    assert agent.check_password(PASSWORD)


def test_migration_closes_agent_sessions_only(mar_agent, customer_client):
    agent_token = Token.objects.create(user=mar_agent)
    customer_tokens = Token.objects.exclude(user=mar_agent).count()
    migration = import_module("apps.accounts.migrations.0002_pro_login")

    migration.close_agent_sessions(django_apps, None)

    assert not Token.objects.filter(key=agent_token.key).exists()
    assert Token.objects.count() == customer_tokens >= 1


def test_seed_creates_demo_staff_and_company_only_in_demo_mode(db, settings):
    from apps.backoffice.permissions import STAFF_GROUP
    from apps.companies.models import Company

    settings.DEMO_MODE, settings.DEMO_PASSWORD = False, DEMO_PASSWORD
    call_command("seed_demo", verbosity=0)
    assert not User.objects.filter(role=User.Role.STAFF).exists()
    assert not Company.objects.exists()

    settings.DEMO_MODE = True
    call_command("seed_demo", verbosity=0)
    call_command("seed_demo", verbosity=0)  # relançable sans doublon
    staff = User.objects.get(phone="+22230000000", role=User.Role.STAFF)
    # Compte équipe démo : droits métier du groupe, jamais superutilisateur.
    assert staff.is_staff and not staff.is_superuser and staff.check_password(DEMO_PASSWORD)
    assert staff.groups.filter(name=STAFF_GROUP).exists()
    assert staff.has_perm("companies.change_company") and not staff.has_perm("auth.change_group")
    company = Company.objects.get(nif="DEMO00001")
    assert company.status == Company.Status.VERIFIED
    assert step1(APIClient(), email="entreprise@demo.test", password=DEMO_PASSWORD).status_code == 200


def test_seed_demo_without_password_leaves_accounts_unusable(db, settings):
    settings.DEMO_MODE, settings.DEMO_PASSWORD = True, ""
    call_command("seed_demo", verbosity=0)
    assert not User.objects.get(phone="+22230000000", role=User.Role.STAFF).has_usable_password()


def test_demo_staff_was_superuser_is_demoted(db, settings):
    settings.DEMO_MODE, settings.DEMO_PASSWORD = True, DEMO_PASSWORD
    User.objects.create_user("+22230000000", role=User.Role.STAFF, is_staff=True, is_superuser=True)
    call_command("seed_demo", verbosity=0)
    assert not User.objects.get(phone="+22230000000", role=User.Role.STAFF).is_superuser
