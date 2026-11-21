"""Réglages Django de la plateforme Sanad.

Toute valeur sensible vient de variables d'environnement ; voir .env.example.
Production par défaut : DEBUG est faux sauf DJANGO_DEBUG=1 (développement local), et
config/production.py refuse de démarrer si une variable indispensable manque.
"""
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from .production import DEV_SECRET_KEY, DEV_SIMULATED_SECRET, production_errors

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path):
    """Charge le .env de la racine du dépôt s'il existe (développement local).

    Les variables déjà définies dans l'environnement gardent la priorité.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


# DJANGO_ENV_FILE : autre fichier (ou aucun) ; sert aux tests de démarrage en production.
_load_dotenv(Path(os.environ.get("DJANGO_ENV_FILE") or BASE_DIR.parent / ".env"))


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return env(name, str(default)).lower() in {"1", "true", "yes", "on"}


SECRET_KEY = env("DJANGO_SECRET_KEY", DEV_SECRET_KEY)
# Faux par défaut : une variable oubliée ne doit jamais ouvrir le mode développement en ligne.
DEBUG = env_bool("DJANGO_DEBUG", False)
# Démonstration : simulateurs (paiement, registre d'identité), comptes démo et reset_demo.
# Distinct de DEBUG ; ne lève aucune autre protection de production.
DEMO_MODE = env_bool("DEMO_MODE", False)
DEMO_PASSWORD = env("DEMO_PASSWORD", "")  # mot de passe des comptes démo : jamais dans le code
ALLOWED_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]
# Le back-office est servi à travers l'app (http://localhost:3000/admin/) : son origine doit être acceptée
# par la protection CSRF du formulaire de connexion. En production : https://<domaine>.
CSRF_TRUSTED_ORIGINS = [o for o in env("CSRF_TRUSTED_ORIGINS", "http://localhost:3000").split(",") if o]

INSTALLED_APPS = [
    "apps.backoffice.apps.BackofficeConfig",  # avant l'admin : ses gabarits remplacent ceux de Django
    "apps.backoffice.apps.BackofficeAdminConfig",  # admin Django avec le site de Sanad
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
    "apps.companies",
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

AUTHENTICATION_BACKENDS = ["apps.accounts.backends.PhonePasswordBackend"]
# Le téléphone (USERNAME_FIELD) n'est unique que pour les comptes particuliers : voir accounts/backends.py.
SILENCED_SYSTEM_CHECKS = ["auth.W004"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "fr"
LANGUAGES = [("fr", "Français"), ("ar", "العربية")]
# Traductions arabes du back-office (le français est la langue des sources).
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Africa/Nouakchott"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", BASE_DIR / "media"))
# Pièces d'identité : hors de MEDIA_ROOT, jamais servies publiquement (voir accounts/storage.py).
PRIVATE_MEDIA_ROOT = Path(env("PRIVATE_MEDIA_ROOT") or BASE_DIR / "private_media")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.TokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "otp": env("OTP_THROTTLE_RATE", "5/hour"),
        "verify": "120/minute",
        "pro_login": env("PRO_LOGIN_THROTTLE_RATE", "30/hour"),  # par adresse IP
        "password": env("PASSWORD_THROTTLE_RATE", "10/hour"),
        "scan": env("SCAN_THROTTLE_RATE", "20/hour"),
        "identity": env("IDENTITY_THROTTLE_RATE", "5/hour"),  # interrogations du registre national, par compte  # lecture de carte grise : payante, par compte
    },
}

# --- Métier -----------------------------------------------------------------

PLATFORM_NAME = env("PLATFORM_NAME", "Sanad")
CURRENCY = "MRU"

OTP_TTL_SECONDS = int(env("OTP_TTL_SECONDS", 300))
OTP_MAX_ATTEMPTS = int(env("OTP_MAX_ATTEMPTS", 5))

# Comptes professionnels (agents assureurs) : email + mot de passe + code SMS.
PRO_LOGIN_MAX_FAILURES = int(env("PRO_LOGIN_MAX_FAILURES", 5))
PRO_LOGIN_LOCK_MINUTES = int(env("PRO_LOGIN_LOCK_MINUTES", 15))
# Back-office : code SMS après le mot de passe. Désactivable en développement seulement.
BACKOFFICE_SMS_CODE = env_bool("BACKOFFICE_SMS_CODE", True)
PASSWORD_RESET_TIMEOUT = 72 * 3600  # lien d'invitation ou de réinitialisation : 72 h
PORTAL_BASE_URL = env("PORTAL_BASE_URL", "http://localhost:3000")  # liens envoyés par email

# E-mail : affiché dans la console en développement, SMTP en production.
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = int(env("EMAIL_PORT", 587))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Sanad <no-reply@localhost>")

# Clé Ed25519 (graine de 32 octets en base64) qui signe les attestations.
# En production, elle vient d'un coffre de clés ; jamais du dépôt.
ATTESTATION_SIGNING_KEY = env("ATTESTATION_SIGNING_KEY", "")
ATTESTATION_VERIFY_BASE_URL = env("ATTESTATION_VERIFY_BASE_URL", "http://localhost:8000/v/")
ATTESTATION_NUMBER_PREFIX = env("ATTESTATION_NUMBER_PREFIX", "SN")
# Tant qu'aucun partenariat n'est signé, le PDF porte la mention « SPÉCIMEN, sans valeur d'assurance ».
ATTESTATION_SPECIMEN = env_bool("ATTESTATION_SPECIMEN", True)

# Fournisseurs de paiement actifs. "simulated" n'existe que hors production.
PAYMENT_PROVIDERS = [p for p in env("PAYMENT_PROVIDERS", "simulated").split(",") if p]
PAYMENT_CALLBACK_SECRETS = {
    "simulated": env("SIMULATED_CALLBACK_SECRET", DEV_SIMULATED_SECRET),
    "bankily": env("BANKILY_CALLBACK_SECRET", ""),
    "masrvi": env("MASRVI_CALLBACK_SECRET", ""),
    "sedad": env("SEDAD_CALLBACK_SECRET", ""),
}

# Plafond d'une transaction mobile money (MRU) ; 0 = pas de plafond. À renseigner avec les opérateurs.
PAYMENT_MAX_AMOUNT = int(env("PAYMENT_MAX_AMOUNT", 0))
# Bouton « simuler la confirmation » : développement ou démonstration uniquement.
ENABLE_PAYMENT_SIMULATOR = (DEBUG or DEMO_MODE) and "simulated" in PAYMENT_PROVIDERS

# Vérification d'identité au registre national : "simulated" (développement),
# "anrpts" quand l'adaptateur existera, vide = désactivée (pièces vérifiées à la main).
IDENTITY_PROVIDER = env("IDENTITY_PROVIDER", "simulated" if DEBUG or DEMO_MODE else "")

# Lecture de la carte grise par Claude (vision). Sans clé, le bouton répond
# « lecture indisponible » et le client saisit les champs à la main.
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", "")
REGISTRATION_SCAN_MODEL = env("REGISTRATION_SCAN_MODEL", "claude-opus-5-5")

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
    _errors = production_errors(globals())
    if _errors:
        raise ImproperlyConfigured(
            "Configuration de production refusée (DJANGO_DEBUG=1 pour le développement local) :\n- "
            + "\n- ".join(_errors)
        )

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    # fontTools (sous-ensemble des polices du PDF) est très bavard au niveau INFO.
    "loggers": {"fontTools": {"level": "WARNING"}},
}
