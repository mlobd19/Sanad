"""Garde-fous de production : Sanad refuse de démarrer plutôt que de tourner mal configuré.

Appelé à la fin de settings.py dès que DEBUG est faux (la valeur par défaut). Chaque règle
protège contre une variable d'environnement oubliée. DEMO_MODE autorise seulement les
simulateurs (paiement, registre d'identité) : il ne lève aucune autre protection.
"""

DEV_SECRET_KEY = "dev-only-insecure-key-change-me"
DEV_SIMULATED_SECRET = "dev-simulated-secret"

# Backends qui écrivent dans la console, la mémoire ou un fichier au lieu d'envoyer réellement.
DEV_NOTIFICATION_BACKENDS = ("ConsoleBackend", "MemoryBackend")
DEV_EMAIL_BACKENDS = ("console", "locmem", "dummy", "filebased")


def production_errors(conf: dict) -> list[str]:
    """Liste des raisons de refuser le démarrage (vide = configuration acceptable)."""
    errors = []
    demo = bool(conf.get("DEMO_MODE"))

    secret = conf.get("SECRET_KEY") or ""
    if not secret or secret == DEV_SECRET_KEY:
        errors.append("DJANGO_SECRET_KEY absente ou égale à la valeur de développement.")

    engine = conf["DATABASES"]["default"].get("ENGINE", "")
    if "sqlite" in engine:
        errors.append("Base SQLite interdite : renseigner DATABASE_URL (PostgreSQL).")
    elif "postgresql" not in engine:
        errors.append(f"Base non prise en charge ({engine}) : PostgreSQL attendu via DATABASE_URL.")

    notification = conf.get("NOTIFICATION_BACKEND") or ""
    if not notification or notification.rsplit(".", 1)[-1] in DEV_NOTIFICATION_BACKENDS:
        errors.append("NOTIFICATION_BACKEND est un backend de développement (console) : brancher le fournisseur SMS.")

    email = conf.get("EMAIL_BACKEND") or ""
    parts = email.split(".")
    if not email or (len(parts) >= 2 and parts[-2] in DEV_EMAIL_BACKENDS):
        errors.append("EMAIL_BACKEND est un backend de développement (console) : utiliser SMTP.")

    errors += _payment_errors(conf.get("PAYMENT_PROVIDERS") or [], conf.get("PAYMENT_CALLBACK_SECRETS") or {}, demo)

    if conf.get("IDENTITY_PROVIDER") == "simulated" and not demo:
        errors.append("Le registre d'identité simulé est interdit en production (hors DEMO_MODE).")
    if conf.get("BACKOFFICE_2FA") != "totp":
        errors.append("BACKOFFICE_2FA doit valoir « totp » en production : application d'authentification "
                      "obligatoire pour l'équipe (le code SMS n'est permis qu'en DEBUG).")
    if not conf.get("ATTESTATION_SIGNING_KEY"):
        errors.append("ATTESTATION_SIGNING_KEY est obligatoire en production.")
    if demo and len(conf.get("DEMO_PASSWORD") or "") < 12:
        errors.append("DEMO_MODE en ligne : DEMO_PASSWORD doit faire au moins 12 caractères.")
    return errors


def _payment_errors(providers: list[str], secrets: dict, demo: bool) -> list[str]:
    from apps.payments.providers import REGISTRY  # n'importe que la bibliothèque standard et django.conf

    errors = []
    if not providers:
        errors.append("PAYMENT_PROVIDERS est vide : aucun moyen de paiement.")
    for name in providers:
        adapter = REGISTRY.get(name)
        if adapter is None or not adapter.implemented:
            errors.append(f"Fournisseur de paiement « {name} » sans adaptateur opérationnel.")
            continue
        if name == "simulated" and not demo:
            errors.append("Le fournisseur de paiement simulé est interdit en production (hors DEMO_MODE).")
        secret = secrets.get(name) or ""
        if not secret or secret == DEV_SIMULATED_SECRET:
            errors.append(f"Fournisseur de paiement « {name} » sans secret de callback (ou secret de développement).")
    return errors
