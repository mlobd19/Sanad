"""Alertes à l'équipe (toutes les 15 min, Celery) : paiements bloqués et messages en échec.

Chaque passage ne signale que ce qui est apparu depuis le précédent : un paiement l'est une fois,
quand il dépasse 1 h d'attente ; un échec d'envoi l'est une fois, dans les 15 min qui suivent.
Destinataires : les membres actifs du groupe « Équipe Sanad » qui ont un e-mail.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .permissions import STAFF_GROUP

logger = logging.getLogger("monitoring")

CHECK_EVERY = timedelta(minutes=15)
PAYMENT_STUCK_AFTER = timedelta(hours=1)


def team_emails() -> list[str]:
    from apps.accounts.models import User

    return sorted(set(
        User.objects.filter(groups__name=STAFF_GROUP, is_active=True, is_staff=True)
        .exclude(email__isnull=True).exclude(email="").values_list("email", flat=True)
    ))


def collect_alerts(now=None) -> list[str]:
    """Lignes d'alerte pour la fenêtre des 15 dernières minutes (vide = rien à signaler)."""
    from apps.notifications.models import NotificationFailure
    from apps.payments.models import Payment

    now = now or timezone.now()
    lines = []
    stuck = Payment.objects.filter(status=Payment.Status.PENDING, created_at__lte=now - PAYMENT_STUCK_AFTER,
                                   created_at__gt=now - PAYMENT_STUCK_AFTER - CHECK_EVERY)
    for payment in stuck.order_by("created_at"):
        lines.append(f"Paiement en attente depuis plus d'1 h : {payment.provider} · {payment.amount} MRU · "
                     f"réf. {payment.external_ref or payment.pk}")
    failures = NotificationFailure.objects.filter(created_at__gt=now - CHECK_EVERY)
    if failures.exists():
        by_channel = {}
        for failure in failures:
            by_channel[failure.channel] = by_channel.get(failure.channel, 0) + 1
        detail = ", ".join(f"{n} {channel}" for channel, n in sorted(by_channel.items()))
        lines.append(f"Envois en échec dans les 15 dernières minutes : {detail} "
                     "(back-office › Technique › Envois en échec).")
    return lines


def alert_team(now=None) -> int:
    """Envoie l'alerte par e-mail ; renvoie le nombre de lignes signalées."""
    lines = collect_alerts(now)
    if not lines:
        return 0
    recipients = team_emails()
    if not recipients:
        logger.error("Alerte sans destinataire (aucun membre de « %s » avec un e-mail) : %s", STAFF_GROUP, lines)
        return len(lines)
    body = "Bonjour,\n\nÀ vérifier dans le back-office de Sanad :\n\n" + "\n".join(f"- {line}" for line in lines)
    send_mail(f"[{settings.PLATFORM_NAME}] {len(lines)} alerte(s) à vérifier", body,
              settings.DEFAULT_FROM_EMAIL, recipients)
    return len(lines)
