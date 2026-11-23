"""Surveillance : Sentry (erreurs) si SENTRY_DSN est défini, sans aucune donnée personnelle."""
import re

_SECRETS = re.compile(r"https?://\S+|\b\d{4,}\b")


def _clean(text):
    return _SECRETS.sub("•", text) if isinstance(text, str) else text


def _scrub(event, hint):
    """Filet de sécurité : masque chiffres (codes, numéros) et liens dans les messages d'erreur envoyés."""
    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        for key in ("message", "formatted"):
            logentry[key] = _clean(logentry.get(key))
        logentry.pop("params", None)  # valeurs injectées dans le message : peuvent contenir un numéro
    if "message" in event:
        event["message"] = _clean(event["message"])
    for exc in (event.get("exception") or {}).get("values") or []:
        exc["value"] = _clean(exc.get("value"))
    return event


def init_sentry(dsn: str, environment: str, debug: bool = False) -> bool:
    """Active Sentry pour Django et Celery. Faux (et rien d'envoyé) si aucun DSN."""
    if not dsn:
        return False
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        # Aucune donnée personnelle. data_collection remplace send_default_pii=False dans sentry-sdk 2.75
        # (l'ancienne option est dépréciée) et va plus loin, catégorie par catégorie :
        data_collection={
            "user_info": False,  # ni compte, ni adresse IP
            "cookies": {"mode": "off"},
            "http_headers": {"request": {"mode": "off"}},
            "http_bodies": [],  # jamais le corps des requêtes (numéros, codes, NNI…)
            "url_query_params": {"mode": "off"},  # liens de mot de passe : uid et jeton dans l'adresse
            "database_query_data": False,
            "stack_frame_variables": False,  # les variables du code peuvent contenir un numéro ou un code SMS
            "gen_ai": {"inputs": False, "outputs": False},
        },
        traces_sample_rate=0.0,
        before_send=_scrub,
        debug=debug,
    )
    return True
