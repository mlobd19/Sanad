"""Réglages Django de la plateforme Sanad.

Toute valeur sensible vient de variables d'environnement ; voir .env.example.
"""
import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return env(name, str(default)).lower() in {"1", "true", "yes", "on"}


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "apps.audit",
    "apps.accounts",
    "apps.catalog",
    "apps.policies",
    "apps.payments",
    "apps.attestations",
    "apps.notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}"), conn_max_age=60
    )
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "fr"
LANGUAGES = [("fr", "Français"), ("ar", "العربية")]
TIME_ZONE = "Africa/Nouakchott"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", BASE_DIR / "media"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.TokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"otp": env("OTP_THROTTLE_RATE", "5/hour"), "verify": "120/minute"},
}

# --- Métier -----------------------------------------------------------------

PLATFORM_NAME = env("PLATFORM_NAME", "Sanad")
CURRENCY = "MRU"

OTP_TTL_SECONDS = int(env("OTP_TTL_SECONDS", 300))
OTP_MAX_ATTEMPTS = int(env("OTP_MAX_ATTEMPTS", 5))

# Clé Ed25519 (graine de 32 octets en base64) qui signe les attestations.
# En production, elle vient d'un coffre de clés ; jamais du dépôt.
ATTESTATION_SIGNING_KEY = env("ATTESTATION_SIGNING_KEY", "")
ATTESTATION_VERIFY_BASE_URL = env("ATTESTATION_VERIFY_BASE_URL", "http://localhost:8000/v/")
ATTESTATION_NUMBER_PREFIX = env("ATTESTATION_NUMBER_PREFIX", "SN")

# Fournisseurs de paiement actifs. "simulated" n'existe que hors production.
PAYMENT_PROVIDERS = [p for p in env("PAYMENT_PROVIDERS", "simulated").split(",") if p]
PAYMENT_CALLBACK_SECRETS = {
    "simulated": env("SIMULATED_CALLBACK_SECRET", "dev-simulated-secret"),
    "bankily": env("BANKILY_CALLBACK_SECRET", ""),
    "masrvi": env("MASRVI_CALLBACK_SECRET", ""),
    "sedad": env("SEDAD_CALLBACK_SECRET", ""),
}

# Bouton « simuler la confirmation » de l'app client : développement uniquement.
ENABLE_PAYMENT_SIMULATOR = DEBUG and "simulated" in PAYMENT_PROVIDERS

NOTIFICATION_BACKEND = env("NOTIFICATION_BACKEND", "apps.notifications.backends.ConsoleBackend")

RENEWAL_REMINDER_DAYS = [30, 7, 1]

CELERY_BROKER_URL = env("REDIS_URL", "redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", True)
CELERY_TIMEZONE = TIME_ZONE

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = 31536000
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    if "simulated" in PAYMENT_PROVIDERS:
        raise RuntimeError("Le fournisseur de paiement simulé est interdit en production.")
    if not ATTESTATION_SIGNING_KEY:
        raise RuntimeError("ATTESTATION_SIGNING_KEY est obligatoire en production.")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
