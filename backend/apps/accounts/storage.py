"""Stockage privé des pièces d'identité : hors de MEDIA_ROOT, jamais servi par une URL publique.

Les fichiers ne s'ouvrent que par le back-office (vue réservée à l'équipe, chaque
consultation journalisée). Dossier : PRIVATE_MEDIA_ROOT.
"""
import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible(path="apps.accounts.storage.PrivateStorage")
class PrivateStorage(FileSystemStorage):
    # Lu à chaque accès : suit PRIVATE_MEDIA_ROOT, y compris quand les tests le changent.
    @property
    def base_location(self):
        return str(settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None

    def url(self, name):
        raise ValueError("Fichier privé : pas d'URL publique.")
