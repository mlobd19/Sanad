"""Production sûre même si une variable est oubliée : un test par refus de démarrage."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from config.production import DEV_SECRET_KEY, DEV_SIMULATED_SECRET, production_errors

BACKEND = Path(__file__).resolve().parent.parent


def good_conf(**overrides) -> dict:
    """Configuration de production correcte ; chaque test en casse une seule partie."""
    conf = {
        "SECRET_KEY": "x" * 50,
        "DATABASES": {"default": {"ENGINE": "django.db.backends.postgresql"}},
        "NOTIFICATION_BACKEND": "apps.notifications.backends.SmsProviderBackend",
        "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "PAYMENT_PROVIDERS": ["simulated"],
        "PAYMENT_CALLBACK_SECRETS": {"simulated": "secret-de-production-solide"},
        "IDENTITY_PROVIDER": "",
        "BACKOFFICE_2FA": "totp",
        "NUM_PROXIES_EXPLICIT": True,
        "ATTESTATION_SIGNING_KEY": "graine",
        "DEMO_MODE": True,  # seul fournisseur prêt aujourd'hui : le simulateur, permis en démonstration
        "DEMO_PASSWORD": "Mot-de-passe-demo-2026",
    }
    conf.update(overrides)
    return conf


def refused(conf: dict, fragment: str) -> bool:
    return any(fragment in e for e in production_errors(conf))


def test_good_configuration_starts():
    assert production_errors(good_conf()) == []


# --- Clé secrète -----------------------------------------------------------------------------

def test_refuses_missing_secret_key():
    assert refused(good_conf(SECRET_KEY=""), "DJANGO_SECRET_KEY")


def test_refuses_development_secret_key():
    assert refused(good_conf(SECRET_KEY=DEV_SECRET_KEY), "DJANGO_SECRET_KEY")


# --- Base de données ----------------------------------------------------------------------------

def test_refuses_sqlite():
    conf = good_conf(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3"}})
    assert refused(conf, "SQLite")


def test_refuses_non_postgresql_database():
    assert refused(good_conf(DATABASES={"default": {"ENGINE": "django.db.backends.mysql"}}), "PostgreSQL")


# --- Envois (SMS, e-mail) ------------------------------------------------------------------------

@pytest.mark.parametrize("backend", ["apps.notifications.backends.ConsoleBackend",
                                     "apps.notifications.backends.MemoryBackend", ""])
def test_refuses_console_notification_backend(backend):
    assert refused(good_conf(NOTIFICATION_BACKEND=backend), "NOTIFICATION_BACKEND")


@pytest.mark.parametrize("backend", ["django.core.mail.backends.console.EmailBackend",
                                     "django.core.mail.backends.locmem.EmailBackend", ""])
def test_refuses_console_email_backend(backend):
    assert refused(good_conf(EMAIL_BACKEND=backend), "EMAIL_BACKEND")


# --- Paiement ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("provider", ["bankily", "masrvi", "sedad", "inconnu"])
def test_refuses_provider_without_adapter(provider):
    conf = good_conf(PAYMENT_PROVIDERS=[provider], PAYMENT_CALLBACK_SECRETS={provider: "secret"})
    assert refused(conf, "sans adaptateur")


@pytest.mark.parametrize("secret", ["", DEV_SIMULATED_SECRET])
def test_refuses_provider_without_secret(secret):
    assert refused(good_conf(PAYMENT_CALLBACK_SECRETS={"simulated": secret}), "sans secret")


def test_refuses_empty_provider_list():
    assert refused(good_conf(PAYMENT_PROVIDERS=[]), "PAYMENT_PROVIDERS est vide")


def test_refuses_simulated_payment_outside_demo_mode():
    assert refused(good_conf(DEMO_MODE=False), "paiement simulé")


# --- Autres protections -------------------------------------------------------------------------------

def test_refuses_simulated_identity_outside_demo_mode():
    assert refused(good_conf(DEMO_MODE=False, IDENTITY_PROVIDER="simulated"), "registre d'identité simulé")
    assert production_errors(good_conf(IDENTITY_PROVIDER="simulated")) == []  # permis en démonstration


@pytest.mark.parametrize("method", ["sms", "off", ""])
def test_totp_is_mandatory_for_the_backoffice_in_production(method):
    assert refused(good_conf(BACKOFFICE_2FA=method), "BACKOFFICE_2FA")


def test_refuses_missing_signing_key():
    assert refused(good_conf(ATTESTATION_SIGNING_KEY=""), "ATTESTATION_SIGNING_KEY")


@pytest.mark.parametrize("password", ["", "court"])
def test_refuses_demo_mode_without_strong_demo_password(password):
    assert refused(good_conf(DEMO_PASSWORD=password), "DEMO_PASSWORD")


def test_demo_mode_does_not_lift_other_protections():
    conf = good_conf(SECRET_KEY="", DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3"}},
                     NOTIFICATION_BACKEND="apps.notifications.backends.ConsoleBackend")
    errors = production_errors(conf)
    assert len(errors) == 3 and conf["DEMO_MODE"]


# --- De bout en bout : Django refuse vraiment de démarrer ----------------------------------------------

def start_django(**env) -> subprocess.CompletedProcess:
    """Démarre Django dans un processus neuf, sans le .env local, avec seulement `env` en plus."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "DEMO_", "DATABASE_URL"))}
    clean.update(DJANGO_SETTINGS_MODULE="config.settings", DJANGO_ENV_FILE="/nonexistent/.env", **env)
    return subprocess.run([sys.executable, "-c", "import django; django.setup(); print('démarré')"],
                          cwd=BACKEND, env=clean, capture_output=True, text=True, timeout=60)


def test_debug_is_off_by_default_and_production_refuses_to_start():
    result = start_django()  # aucune variable : DEBUG faux, donc garde-fous de production
    assert result.returncode != 0
    assert "Configuration de production refusée" in result.stderr
    for reason in ("DJANGO_SECRET_KEY", "SQLite", "NOTIFICATION_BACKEND", "EMAIL_BACKEND", "paiement simulé"):
        assert reason in result.stderr, reason


def test_local_development_still_starts_with_django_debug():
    result = start_django(DJANGO_DEBUG="1")
    assert result.returncode == 0, result.stderr
    assert "démarré" in result.stdout
