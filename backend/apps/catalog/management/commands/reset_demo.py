"""Remet la démo à zéro : base vidée, fichiers déposés effacés, catalogue de démo recréé.

    python manage.py reset_demo          # demande confirmation
    python manage.py reset_demo --yes    # sans confirmation

Réservé au développement : refuse de s'exécuter quand DEBUG est faux, pour
qu'aucune donnée réelle ne puisse être effacée par erreur.
"""
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from .seed_demo import DEMO_AGENT_PASSWORD, DEMO_COMPANY_EMAIL, DEMO_STAFF_PHONE


def _empty_dir(folder: Path) -> None:
    """Vide un dossier sans le supprimer (il peut être un volume monté)."""
    if not folder.is_dir():
        return
    for child in folder.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


class Command(BaseCommand):
    help = "Efface toutes les données locales et recrée la démo (développement uniquement)."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="ne pas demander de confirmation")
        parser.add_argument("--logos", default=str(settings.BASE_DIR / "logos"),
                            help="dossier des logos officiels à réimporter (défaut : backend/logos)")

    def handle(self, yes=False, logos="", **options):
        if not settings.DEBUG:
            raise CommandError("reset_demo est réservé au développement (DEBUG faux) : rien n'a été effacé.")

        if not yes:
            self.stdout.write(self.style.WARNING(
                "Toutes les données locales vont être effacées : comptes, véhicules, contrats, paiements, "
                "sinistres et pièces déposées. Le code et les logos de backend/logos/ ne sont pas touchés."
            ))
            if input("Taper « oui » pour continuer : ").strip().lower() != "oui":
                raise CommandError("Annulé : rien n'a été effacé.")

        quiet = {"verbosity": 0}
        call_command("flush", interactive=False, **quiet)
        _empty_dir(Path(settings.PRIVATE_MEDIA_ROOT))  # pièces d'identité, NIF / RC, photos de sinistre
        _empty_dir(Path(settings.MEDIA_ROOT) / "insurers")  # anciennes copies des logos
        call_command("seed_demo", **quiet)

        logos_dir = Path(logos)
        if logos_dir.is_dir():
            call_command("import_logos", str(logos_dir), stdout=self.stdout)
        else:
            self.stdout.write(f"Pas de dossier de logos ({logos_dir}) : compagnies sans logo.")

        self.stdout.write(self.style.SUCCESS(
            f"Démo réinitialisée. Agents : agent@<code>.test, équipe : {DEMO_STAFF_PHONE}, "
            f"entreprise : {DEMO_COMPANY_EMAIL} (mot de passe {DEMO_AGENT_PASSWORD})."
        ))
