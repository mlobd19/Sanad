"""Supprime les connexions expirées (aussi lancé chaque nuit par Celery : accounts.tasks)."""
from django.core.management.base import BaseCommand

from apps.accounts.tokens import purge_expired


class Command(BaseCommand):
    help = "Supprime les jetons de connexion expirés."

    def handle(self, **options):
        self.stdout.write(f"{purge_expired()} connexion(s) expirée(s) supprimée(s).")
