from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig


class BackofficeAdminConfig(AdminConfig):
    """Remplace le site d'administration par défaut par celui de Sanad (accueil « À traiter », menu par métier)."""

    default_site = "apps.backoffice.site.SanadAdminSite"


class BackofficeConfig(AppConfig):
    """Gabarits, styles, traductions et commandes du back-office (déclarée avant l'admin pour en remplacer les gabarits)."""

    name = "apps.backoffice"
    label = "backoffice"
    default_auto_field = "django.db.models.BigAutoField"
