from celery import shared_task
from django.conf import settings

from apps.notifications.service import notify

from . import services


@shared_task
def send_renewal_reminders():
    sent = 0
    for days in settings.RENEWAL_REMINDER_DAYS:
        for policy in services.policies_due_for_reminder(days):
            if policy.renewals.exists():
                continue
            notify(
                "whatsapp",
                policy.customer.phone,
                "renewal_reminder",
                {"plate": policy.asset.reference, "days": days},
                language=policy.customer.language,
            )
            sent += 1
    return sent


@shared_task
def expire_due_policies():
    return services.expire_policies()
