from django.db import models
from django.utils.translation import gettext_lazy as _


def mask_recipient(to: str) -> str:
    """Destinataire masqué : « +222 •• •• •• 01 » ou « a•••@domaine.mr » (jamais en clair dans les journaux)."""
    to = to or ""
    if "@" in to:
        name, _, domain = to.partition("@")
        return f"{name[:1]}•••@{domain}"
    return f"{to[:4]} •• •• •• {to[-2:]}" if len(to) >= 6 else "••"


class NotificationFailure(models.Model):
    """Message qui n'a pas pu partir (SMS, e-mail). L'équipe est prévenue (backoffice/monitoring.py)."""

    channel = models.CharField(max_length=10, verbose_name=_("canal"))
    recipient = models.CharField(max_length=80, verbose_name=_("destinataire (masqué)"))
    template = models.CharField(max_length=40, verbose_name=_("message"))
    error = models.CharField(max_length=255, blank=True, verbose_name=_("erreur"))
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name=_("date"))

    class Meta:
        verbose_name = _("envoi en échec")
        verbose_name_plural = _("envois en échec")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.channel} · {self.template} · {self.created_at:%Y-%m-%d %H:%M}"
