"""Limites des codes SMS, NUM_PROXIES explicite, Sentry sans données personnelles, alertes et santé."""
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from django.core import mail
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.backoffice.permissions import staff_group
from apps.notifications.models import NotificationFailure
from apps.notifications.service import notify
from apps.payments.models import Payment
from config.monitoring import _scrub, init_sentry
from config.production import production_errors

from .test_production_settings import good_conf

BACKEND = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.django_db


# --- 10. Limites des codes SMS ------------------------------------------------------------------------

def test_ip_limit_for_sms_codes_is_60_per_hour(settings):
    # Une adresse d'opérateur mobile est partagée : la vraie limite est par numéro (5/heure).
    assert settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["otp"] == "60/hour"
    assert settings.OTP_MAX_SMS_PER_PHONE_PER_HOUR == 5


def test_production_refuses_implicit_num_proxies():
    assert any("NUM_PROXIES" in e for e in production_errors(good_conf(NUM_PROXIES_EXPLICIT=False)))
    assert production_errors(good_conf(NUM_PROXIES_EXPLICIT=True)) == []


@pytest.mark.parametrize("env, explicit", [({}, False), ({"NUM_PROXIES": "1"}, True), ({"NUM_PROXIES": "0"}, True)])
def test_num_proxies_explicit_means_defined_in_environment(env, explicit):
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "DEMO_", "NUM_PROXIES"))}
    clean.update(DJANGO_SETTINGS_MODULE="config.settings", DJANGO_ENV_FILE="/nonexistent/.env", DJANGO_DEBUG="1", **env)
    out = subprocess.run([sys.executable, "-c", "import django; django.setup(); from django.conf import settings; "
                          "print(settings.NUM_PROXIES_EXPLICIT)"], cwd=BACKEND, env=clean,
                         capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == str(explicit), out.stderr


# --- 8. Sentry ------------------------------------------------------------------------------------------

def test_sentry_off_without_dsn(settings):
    assert init_sentry("", "test") is False
    assert settings.SENTRY_ENABLED is False


def test_sentry_never_sends_personal_data():
    import sentry_sdk

    try:
        assert init_sentry("https://public@sentry.example.invalid/1", "test") is True
        collected = sentry_sdk.get_client().options["data_collection"]  # remplace send_default_pii=False
        assert collected["provided_by_user"] and collected["user_info"] is False
        assert collected["http_bodies"] == [] and collected["stack_frame_variables"] is False
        assert collected["cookies"]["mode"] == collected["url_query_params"]["mode"] == "off"
        assert collected["http_headers"]["request"]["mode"] == "off"
    finally:
        sentry_sdk.init()  # client sans DSN : rien n'est envoyé pendant les autres tests

    event = {"logentry": {"message": "Code 482913 pour +22236000001", "params": ["+22236000001"]},
             "exception": {"values": [{"value": "Lien https://app.test/mot-de-passe?token=abc"}]}}
    scrubbed = _scrub(event, None)
    text = str(scrubbed)
    assert "482913" not in text and "36000001" not in text and "token=abc" not in text


# --- 8. Envois en échec ---------------------------------------------------------------------------------

class BrokenSmsBackend:
    def send(self, channel, to, body):
        raise ConnectionError(f"fournisseur injoignable pour {to}")


def test_failed_sms_is_recorded_without_breaking_the_caller(settings):
    settings.NOTIFICATION_BACKEND = "tests.test_monitoring.BrokenSmsBackend"
    assert notify("sms", "+22236000001", "otp", {"code": "123456", "minutes": 5}) is False
    failure = NotificationFailure.objects.get()
    assert failure.channel == "sms" and failure.template == "otp"
    assert failure.recipient == "+222 •• •• •• 01"
    assert "36000001" not in failure.error  # numéro jamais en clair


# --- 8. Alertes à l'équipe ------------------------------------------------------------------------------

@pytest.fixture
def team(db):
    member = User.objects.create_user("+22230000011", role=User.Role.STAFF, is_staff=True, email="ops@sanad.test")
    member.groups.add(staff_group())
    User.objects.create_user("+22230000012", role=User.Role.STAFF, is_staff=True, email="horsgroupe@sanad.test")
    return member


def pending_payment(customer_client, minutes_ago: int) -> Payment:
    from .conftest import buy

    _, pay = buy(customer_client, plate=f"{minutes_ago:04d}AB00")
    payment = Payment.objects.get(external_ref=pay["reference"])
    Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(minutes=minutes_ago))
    return payment


def run_alerts():
    from apps.backoffice.tasks import alert_team_task

    mail.outbox.clear()
    return alert_team_task()


def test_team_alerted_once_when_payment_pending_over_one_hour(customer_client, team):
    pending_payment(customer_client, 65)
    assert run_alerts() == 1
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ["ops@sanad.test"]  # membres du groupe seulement
    assert "Paiement en attente depuis plus d'1 h" in mail.outbox[0].body


def test_no_alert_for_recent_or_already_reported_payments(customer_client, team):
    pending_payment(customer_client, 30)   # moins d'1 h
    pending_payment(customer_client, 120)  # déjà signalé au passage qui a suivi l'heure
    assert run_alerts() == 0 and mail.outbox == []


def test_team_alerted_when_sms_fail(settings, team):
    settings.NOTIFICATION_BACKEND = "tests.test_monitoring.BrokenSmsBackend"
    notify("sms", "+22236000001", "otp", {"code": "123456", "minutes": 5})
    notify("sms", "+22236000002", "otp", {"code": "654321", "minutes": 5})
    assert run_alerts() == 1
    assert "Envois en échec" in mail.outbox[0].body and "2 sms" in mail.outbox[0].body
    assert "36000001" not in mail.outbox[0].body


def test_alert_task_runs_every_15_minutes():
    from config.celery import app

    schedule = app.conf.beat_schedule["alertes-equipe"]
    assert schedule["task"] == "apps.backoffice.tasks.alert_team_task"
    assert schedule["schedule"].minute == {0, 15, 30, 45}


# --- 8. Santé -------------------------------------------------------------------------------------------

def test_health_ok_when_database_answers():
    resp = Client().get("/api/health")
    assert resp.status_code == 200 and resp.json() == {"status": "ok", "database": "ok"}


def test_health_503_when_database_unreachable(monkeypatch):
    from django.db import connection

    def broken():
        raise ConnectionError("base injoignable")

    monkeypatch.setattr(connection, "cursor", broken)
    resp = Client().get("/api/health")
    assert resp.status_code == 503 and resp.json()["database"] == "unreachable"


def test_health_is_exempt_from_https_redirect(settings):
    assert r"^api/health$" in settings.SECURE_REDIRECT_EXEMPT
