from celery import shared_task

from .tokens import purge_expired


@shared_task
def purge_expired_tokens():
    """Nettoyage quotidien des connexions expirées."""
    return purge_expired()
