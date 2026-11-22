"""Durcissement : limite de SMS par numéro, adresse IP non falsifiable, Pillow 13, double couverture au paiement.

Le refus de démarrer en production (point 1) est testé dans test_production_settings.py.
"""
from datetime import timedelta

import PIL
import pytest
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.models import OtpCode
from apps.payments.models import Payment, Refund
from apps.policies.models import Policy

from .conftest import buy, simulate_callback

pytestmark = pytest.mark.django_db


# --- 2. Codes SMS : 5 par numéro et par heure, en plus de la limite par adresse IP ---------------------

def ask_code(phone, ip):
    return APIClient(REMOTE_ADDR=ip).post("/api/auth/otp/request", {"phone": phone}, format="json")


def test_sms_codes_limited_per_number_whatever_the_ip(outbox):
    for i in range(5):
        assert ask_code("36000042", f"10.0.0.{i}").status_code == 202
    blocked = ask_code("36000042", "10.0.0.99")  # nouvelle adresse IP : toujours bloqué
    assert blocked.status_code == 429 and blocked.data["code"] == "sms_rate_limited"
    assert len([m for m in outbox if m["to"] == "+22236000042"]) == 5
    assert ask_code("36000043", "10.0.0.99").status_code == 202  # un autre numéro n'est pas touché


def test_sms_limit_covers_every_journey_and_resets_after_an_hour(demo, outbox):
    from apps.accounts.services import OtpRateLimited, send_code

    for _ in range(5):
        send_code("+22220000002", OtpCode.Purpose.PRO)
    with pytest.raises(OtpRateLimited):
        send_code("+22220000002", OtpCode.Purpose.STAFF)  # back-office, connexion pro, inscription : même compteur
    OtpCode.objects.filter(phone="+22220000002").update(created_at=timezone.now() - timedelta(minutes=61))
    send_code("+22220000002", OtpCode.Purpose.PRO)  # une heure plus tard : de nouveau possible


def test_pro_login_reports_the_sms_limit(demo, settings):
    from apps.accounts.models import User

    agent = User.objects.get(email="agent@mar.test")
    agent.set_password("Agent-MAR-2026-solide")
    agent.save()
    settings.OTP_MAX_SMS_PER_PHONE_PER_HOUR = 1
    login = {"email": "agent@mar.test", "password": "Agent-MAR-2026-solide"}
    assert APIClient().post("/api/auth/pro/login", login, format="json").status_code == 200
    resp = APIClient().post("/api/auth/pro/login", login, format="json")
    assert resp.status_code == 400 and "Trop de codes" in resp.data["detail"]


@pytest.mark.parametrize("proxies, expected", [(0, "203.0.113.7"), (1, "198.51.100.20")])
def test_forwarded_for_header_cannot_be_forged(settings, proxies, expected):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": proxies}
    # Le client écrit lui-même « 1.2.3.4 » ; le relais de confiance ajoute l'adresse réelle à la fin.
    request = RequestFactory().post("/api/auth/otp/request", REMOTE_ADDR="203.0.113.7",
                                    HTTP_X_FORWARDED_FOR="1.2.3.4, 198.51.100.20")
    ident = ScopedRateThrottle().get_ident(request)
    assert ident == expected and ident != "1.2.3.4"


def test_num_proxies_defaults_to_zero():
    from django.conf import settings

    assert settings.REST_FRAMEWORK["NUM_PROXIES"] == 0


# --- 3. Pillow ---------------------------------------------------------------------------------------------

def test_pillow_is_at_least_13():
    assert int(PIL.__version__.split(".")[0]) >= 13


# --- 4. Un véhicule ne peut pas être couvert deux fois : revérifié à la confirmation du paiement -----------

def test_second_paid_policy_for_same_vehicle_is_refused_and_refunded(customer_client, outbox,
                                                                      django_capture_on_commit_callbacks):
    first, pay1 = buy(customer_client, plate="7070KZ00")
    second, pay2 = buy(customer_client, plate="7070 kz 00")  # deux brouillons : autorisés tous les deux
    simulate_callback(APIClient(), pay1["reference"], pay1["amount"])
    with django_capture_on_commit_callbacks(execute=True):
        simulate_callback(APIClient(), pay2["reference"], pay2["amount"])

    assert Policy.objects.get(pk=first["id"]).status == Policy.Status.PAID
    refused = Policy.objects.get(pk=second["id"])
    assert refused.status == Policy.Status.REFUSED  # paid → refused
    assert "déjà couvert" in refused.refusal_reason
    refund = Refund.objects.get(policy=refused)
    assert refund.amount == refused.premium and refund.status == Refund.Status.DONE
    assert Payment.objects.get(external_ref=pay2["reference"]).status == Payment.Status.REFUNDED
    assert any("déjà assuré" in m["body"] for m in outbox)
    assert not refused.attestations.exists()


def test_auto_validating_insurer_never_issues_a_second_attestation(customer_client, auto_insurer):
    first, pay1 = buy(customer_client, plate="8080KZ00", insurer="iman")
    second, pay2 = buy(customer_client, plate="8080KZ00", insurer="iman")
    simulate_callback(APIClient(), pay1["reference"], pay1["amount"])
    simulate_callback(APIClient(), pay2["reference"], pay2["amount"])
    assert Policy.objects.get(pk=first["id"]).status == Policy.Status.ACTIVE
    assert Policy.objects.get(pk=second["id"]).status == Policy.Status.REFUSED
    assert Policy.objects.get(pk=second["id"]).attestations.count() == 0
