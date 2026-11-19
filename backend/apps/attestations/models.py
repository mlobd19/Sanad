from django.conf import settings
from django.db import models


class AttestationCounter(models.Model):
    year = models.PositiveSmallIntegerField(primary_key=True)
    last = models.PositiveIntegerField(default=0)


class Attestation(models.Model):
    class Status(models.TextChoices):
        VALID = "valid", "Valide"
        REVOKED = "revoked", "Révoquée"

    policy = models.ForeignKey("policies.Policy", on_delete=models.PROTECT, related_name="attestations")
    number = models.CharField(max_length=24, unique=True)
    payload = models.JSONField()
    token = models.TextField(unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.VALID, db_index=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return self.number

    @property
    def verify_url(self) -> str:
        return f"{settings.ATTESTATION_VERIFY_BASE_URL}{self.token}"
