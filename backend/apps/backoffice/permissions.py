"""Groupe « Équipe Sanad » : les droits du back-office sans être superutilisateur.

Un compte équipe gère les clients, entreprises, contrats, paiements et le catalogue ; il ne
touche ni aux groupes ni aux permissions, et ne peut pas se donner plus de droits
(voir accounts/admin.py). Le journal d'audit est en lecture seule.
"""
from django.contrib.auth.models import Group, Permission

STAFF_GROUP = "Équipe Sanad"
BUSINESS_APPS = ("accounts", "companies", "catalog", "policies", "payments", "attestations", "notifications")
READ_ONLY_APPS = ("audit",)


def staff_group() -> Group:
    """Crée (ou met à jour) le groupe et lui donne les permissions métier."""
    group, _ = Group.objects.get_or_create(name=STAFF_GROUP)
    perms = Permission.objects.filter(content_type__app_label__in=BUSINESS_APPS) | Permission.objects.filter(
        content_type__app_label__in=READ_ONLY_APPS, codename__startswith="view_")
    group.permissions.set(perms)
    return group
