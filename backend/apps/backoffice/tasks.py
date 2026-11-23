from celery import shared_task

from .monitoring import alert_team


@shared_task
def alert_team_task():
    """Toutes les 15 min : paiements en attente depuis plus d'1 h, messages en échec."""
    return alert_team()
