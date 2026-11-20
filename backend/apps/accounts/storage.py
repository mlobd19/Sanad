"""Stockage privé des pièces justificatives (identité des clients, NIF / RC des entreprises).

Hors de MEDIA_ROOT, jamais servi par une URL publique : les fichiers ne s'ouvrent
que par le back-office (vue réservée à l'équipe, chaque consultation journalisée).
Dossier : PRIVATE_MEDIA_ROOT.
"""
import mimetypes
import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.http import FileResponse, Http404
from django.utils.deconstruct import deconstructible
from PIL import Image, UnidentifiedImageError


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


def detect_document_type(upload) -> str:
    """Extension sûre déduite du contenu (jamais du nom ni du type annoncé) : jpg, png, pdf ou ""."""
    head = upload.read(5)
    upload.seek(0)
    if head == b"%PDF-":
        return "pdf"
    try:
        with Image.open(upload) as img:
            fmt = img.format
            img.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        fmt = None
    finally:
        upload.seek(0)
    return {"JPEG": "jpg", "PNG": "png"}.get(fmt, "")


def private_file_response(field_file) -> FileResponse:
    """Affiche un fichier privé dans le navigateur de l'équipe, sans mise en cache."""
    try:
        handle = field_file.open("rb")
    except FileNotFoundError:
        raise Http404 from None
    content_type = mimetypes.guess_type(field_file.name)[0] or "application/octet-stream"
    response = FileResponse(handle, content_type=content_type)
    response["Content-Disposition"] = "inline"
    response["Cache-Control"] = "private, no-store"
    return response
