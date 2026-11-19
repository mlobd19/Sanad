"""Importe les logos officiels des compagnies depuis un dossier.

Nommer chaque fichier d'après le code de la compagnie : nasr.png, mar.jpg,
medina.webp, iman.png… puis :

    python manage.py import_logos logos/
"""
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from PIL import Image, UnidentifiedImageError

from apps.catalog.models import LOGO_EXTENSIONS, Insurer


class Command(BaseCommand):
    help = "Associe chaque fichier <code>.png|jpg|webp du dossier au logo de la compagnie de même code."

    def add_arguments(self, parser):
        parser.add_argument("folder", nargs="?", default="logos")

    def handle(self, folder, **options):
        root = Path(folder)
        if not root.is_dir():
            raise CommandError(f"Dossier introuvable : {root}")
        done, skipped = [], []
        for path in sorted(root.iterdir()):
            ext = path.suffix.lower().lstrip(".")
            if ext not in LOGO_EXTENSIONS:
                continue
            insurer = Insurer.objects.filter(slug=path.stem.lower()).first()
            if insurer is None:
                skipped.append(f"{path.name} (aucune compagnie « {path.stem} »)")
                continue
            try:
                with Image.open(path) as img:
                    img.verify()
            except (UnidentifiedImageError, OSError):
                skipped.append(f"{path.name} (image illisible)")
                continue
            if insurer.logo:
                insurer.logo.delete(save=False)
            with path.open("rb") as fh:
                insurer.logo.save(f"{insurer.slug}.{ext}", File(fh), save=True)
            done.append(insurer.name)
        for line in skipped:
            self.stdout.write(self.style.WARNING(f"Ignoré : {line}"))
        if done:
            self.stdout.write(self.style.SUCCESS(f"Logos importés : {', '.join(done)}"))
        else:
            self.stdout.write("Aucun logo importé. Codes attendus : " +
                              ", ".join(Insurer.objects.order_by("slug").values_list("slug", flat=True)))
