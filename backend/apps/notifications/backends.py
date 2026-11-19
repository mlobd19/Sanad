import logging

logger = logging.getLogger("notifications")


class ConsoleBackend:
    """Développement : écrit le message dans les logs au lieu de l'envoyer."""

    def send(self, channel, to, body):
        logger.info("[%s → %s] %s", channel, to, body)
        return True


class MemoryBackend:
    """Tests : garde les messages en mémoire pour les inspecter."""

    outbox: list = []

    def send(self, channel, to, body):
        MemoryBackend.outbox.append({"channel": channel, "to": to, "body": body})
        return True
