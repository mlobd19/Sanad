import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("sanad")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(["apps.policies"])

app.conf.beat_schedule = {
    "rappels-renouvellement": {"task": "apps.policies.tasks.send_renewal_reminders", "schedule": crontab(hour=9, minute=0)},
    "expiration-polices": {"task": "apps.policies.tasks.expire_due_policies", "schedule": crontab(hour=0, minute=5)},
}
