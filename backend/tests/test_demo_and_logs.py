"""Mode démo (bandeau, droits du compte équipe) et journaux sans code SMS ni lien hors DEBUG."""
import logging

import pytest
from django.test import Client
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import send_code
from apps.backoffice.permissions import staff_group

pytestmark = pytest.mark.django_db


# --- Journaux ---------------------------------------------------------------------------------

@pytest.fixture
def console(settings):
    settings.NOTIFICATION_BACKEND = "apps.notifications.backends.ConsoleBackend"


def test_sms_code_never_logged_outside_debug(console, settings, caplog):
    settings.DEBUG = False
    with caplog.at_level(logging.INFO, logger="notifications"):
        send_code("+22236000001", "customer")
    logged = caplog.text
    assert "+22236000001" in logged and "••••••" in logged
    assert not any(ch.isdigit() for ch in logged.split("code Sanad", 1)[-1].split(".", 1)[0])


def test_sms_code_visible_in_debug_for_local_login(console, settings, caplog):
    settings.DEBUG = True
    with caplog.at_level(logging.INFO, logger="notifications"):
        send_code("+22236000001", "customer")
    assert "••••••" not in caplog.text


def test_password_link_never_logged_outside_debug(console, settings, caplog, demo):
    settings.DEBUG = False
    agent = User.objects.get(email="agent@mar.test")
    with caplog.at_level(logging.INFO):
        from apps.notifications.service import notify

        notify("whatsapp", agent.phone, "password_reset", {"link": "https://app.test/mot-de-passe?uid=MQ&token=abc",
                                                            "phone": "", "role": "MAR", "name": "Agent"})
    assert "token=abc" not in caplog.text and "[lien masqué]" in caplog.text


# --- Bandeau « Démonstration » ----------------------------------------------------------------------

def test_meta_tells_the_app_about_demo_mode(settings):
    settings.DEMO_MODE = False
    assert APIClient().get("/api/meta").data == {"demo_mode": False}
    settings.DEMO_MODE = True
    assert APIClient().get("/api/meta").data == {"demo_mode": True}


# --- Compte équipe non superutilisateur ----------------------------------------------------------------

@pytest.fixture
def team_member(db):
    user = User.objects.create_user("+22230000009", password="Equipe-Sanad-2026", role=User.Role.STAFF,
                                    is_staff=True, full_name="Membre équipe")
    user.groups.add(staff_group())
    return user


def test_team_member_uses_backoffice_without_being_superuser(team_member):
    client = Client()
    client.force_login(team_member)
    assert client.get("/admin/").status_code == 200
    assert client.get("/admin/companies/company/").status_code == 200
    assert client.get("/admin/auth/group/").status_code == 403  # groupes et permissions : superutilisateur


def test_team_member_cannot_grant_himself_more_rights(team_member):
    from django.contrib.admin.sites import site
    from django.test import RequestFactory

    request = RequestFactory().get("/")
    request.user = team_member
    user_admin = site._registry[User]
    readonly = user_admin.get_readonly_fields(request, team_member)
    assert {"is_superuser", "is_staff", "groups", "user_permissions"} <= set(readonly)

    boss = User.objects.create_superuser("+22230000001", password="Patron-Sanad-2026")
    assert not user_admin.has_change_permission(request, boss)
    assert not user_admin.has_delete_permission(request, boss)
