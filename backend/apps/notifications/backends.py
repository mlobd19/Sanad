import logging
import re

from django.conf import settings

logger = logging.getLogger("notifications")

# Codes SMS (chiffres) et liens (invitation, mot de passe, attestation) : jamais dans les journaux hors DEBUG.
_SECRETS = re.compile(r"https?://\S+|\b\d{4,8}\b")


def redact(text: str) -> str:
    return _SECRETS.sub(lambda m: "[lien masqué]" if m.group(0).startswith("http") else "••••••", text)


class ConsoleBackend:
    """Développement : écrit le message dans les logs au lieu de l'envoyer.

    Le code SMS n'apparaît en clair qu'en DEBUG (pour se connecter en local) ; sinon il est masqué.
    """

    def send(self, channel, to, body):
        logger.info("[%s → %s] %s", channel, to, body if settings.DEBUG else redact(body))
        return True


class MemoryBackend:
    """Tests : garde les messages en mémoire pour les inspecter."""

    outbox: list = []

    def send(self, channel, to, body):
        MemoryBackend.outbox.append({"channel": channel, "to": to, "body": body})
        return True
