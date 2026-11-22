"""Téléphone perdu : supprime l'application d'authentification d'un compte équipe.

    python manage.py reset_totp +22230000000

À la prochaine connexion au back-office, l'équipier scanne un nouveau QR code.
L'opération est journalisée (audit « totp.reset »).
"""
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts import totp
from apps.accounts.models import User, normalize_phone


class Command(BaseCommand):
    help = "Réinitialise l'application d'authentification (TOTP) d'un compte équipe (téléphone perdu)."

    def add_arguments(self, parser):
        parser.add_argument("phone", help="numéro du compte équipe, ex. +22230000000")

    def handle(self, phone, **options):
        try:
            phone = normalize_phone(phone)
        except ValidationError as exc:
            raise CommandError(exc.messages[0]) from None
        user = User.objects.filter(phone=phone, is_staff=True).exclude(role__in=User.PRO_ROLES).first()
        if user is None:
            raise CommandError(f"Aucun compte équipe avec le numéro {phone}.")
        had_device = totp.reset(user, via="manage.py reset_totp")
        if had_device:
            self.stdout.write(self.style.SUCCESS(
                f"Application d'authentification de {user} supprimée : un nouveau QR code sera proposé à la connexion."))
        else:
            self.stdout.write(f"{user} n'avait pas d'application d'authentification enregistrée (journalisé).")
