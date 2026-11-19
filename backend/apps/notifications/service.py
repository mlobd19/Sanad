"""Envoi de messages (SMS, WhatsApp, e-mail) derrière une interface unique.

Le backend réel (agrégateur SMS local, fournisseur WhatsApp Business) se
branche via NOTIFICATION_BACKEND sans toucher au code métier.
"""
from django.conf import settings
from django.utils.module_loading import import_string

TEMPLATES = {
    "otp": {
        "fr": "Votre code {platform} : {code}. Il expire dans {minutes} minutes. Ne le partagez avec personne.",
        "ar": "رمزك في {platform}: {code}. ينتهي خلال {minutes} دقائق. لا تشاركه مع أحد.",
    },
    "attestation_issued": {
        "fr": "Votre attestation d'assurance n° {number} est prête : {url}",
        "ar": "شهادة التأمين رقم {number} جاهزة: {url}",
    },
    "policy_refused": {
        "fr": "L'assureur n'a pas pu valider votre demande. Vous êtes remboursé de {amount} MRU.",
        "ar": "لم تتمكن شركة التأمين من قبول طلبك. سيتم رد مبلغ {amount} أوقية.",
    },
    "renewal_reminder": {
        "fr": "Votre assurance auto ({plate}) expire dans {days} jour(s). Renouvelez-la sur {platform}.",
        "ar": "ينتهي تأمين سيارتك ({plate}) خلال {days} يوم. جدده على {platform}.",
    },
}


def render(template: str, language: str, context: dict) -> str:
    variants = TEMPLATES[template]
    text = variants.get(language) or variants["fr"]
    return text.format(platform=settings.PLATFORM_NAME, **context)


def notify(channel: str, to: str, template: str, context: dict, language: str = "fr"):
    backend = import_string(settings.NOTIFICATION_BACKEND)()
    return backend.send(channel=channel, to=to, body=render(template, language, context))
