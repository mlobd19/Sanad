"""Porte d'entrée unique : /api/me donne le rôle qui oriente vers l'espace ; le SMS seul n'ouvre jamais l'équipe."""
import re

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.notifications.backends import MemoryBackend

from .conftest import login
from .test_company import company_client


@pytest.fixture
def staff(db):
    return User.objects.create_user("+22230000000", password="Equipe-Sanad-2026", role=User.Role.STAFF, is_staff=True)

pytestmark = pytest.mark.django_db


def me_role(user: User) -> str:
    client = APIClient()
    client.force_authenticate(user)
    resp = client.get("/api/me")
    assert resp.status_code == 200
    return resp.data["role"]


def test_me_returns_the_role_of_each_kind_of_account(demo, customer_client, staff):
    assert customer_client.get("/api/me").data["role"] == "customer"
    assert me_role(User.objects.get(email="agent@mar.test")) == "insurer_agent"
    assert company_client().get("/api/me").data["role"] == "company_member"
    assert me_role(staff) == "staff"


def test_sms_alone_never_opens_a_staff_account(demo, staff):
    client = APIClient()
    client.post("/api/auth/otp/request", {"phone": "+22230000000"}, format="json")

    sms = [m for m in MemoryBackend.outbox if m["channel"] == "sms"][-1]
    code = re.search(r"\b(\d{6})\b", sms["body"]).group(1)
    resp = client.post("/api/auth/otp/verify", {"phone": "+22230000000", "code": code}, format="json")
    assert resp.status_code == 400 and "back-office" in resp.data["detail"]
    assert "token" not in resp.data
    assert AuditEvent.objects.filter(action="user.login_failed", data__step="sms_only").exists()
    assert User.objects.filter(phone="+22230000000").count() == 1  # aucun compte particulier créé en douce


def test_customer_sms_login_still_works(demo):
    assert login(APIClient(), "+22236000077")["user"]["role"] == "customer"
