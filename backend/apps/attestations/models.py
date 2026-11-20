from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AttestationCounter(models.Model):
    year = models.PositiveSmallIntegerField(primary_key=True)
    last = models.PositiveIntegerField(default=0)


class Attestation(models.Model):
    class Status(models.TextChoices):
        VALID = "valid", _("Valide")
        REVOKED = "revoked", _("Révoquée")

    policy = models.ForeignKey("policies.Policy", on_delete=models.PROTECT, related_name="attestations", verbose_name=_("police"))
    number = models.CharField(max_length=24, unique=True, verbose_name=_("numéro"))
    payload = models.JSONField(verbose_name=_("contenu signé"))
    token = models.TextField(unique=True, verbose_name=_("jeton"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.VALID, db_index=True, verbose_name=_("statut"))
    issued_at = models.DateTimeField(auto_now_add=True, verbose_name=_("émise le"))
    revoked_at = models.DateTimeField(null=True, blank=True, verbose_name=_("révoquée le"))
    revoked_reason = models.CharField(max_length=255, blank=True, verbose_name=_("motif de révocation"))

    class Meta:
        verbose_name = _("attestation")
        verbose_name_plural = _("attestations")
        ordering = ["-issued_at"]

    def __str__(self):
        return self.number

    @property
    def verify_url(self) -> str:
        return f"{settings.ATTESTATION_VERIFY_BASE_URL}{self.token}"
