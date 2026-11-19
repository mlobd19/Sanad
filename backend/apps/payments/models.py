import uuid

from django.db import models


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente de confirmation"
        SUCCEEDED = "succeeded", "Confirmé"
        FAILED = "failed", "Échoué"
        REFUNDED = "refunded", "Remboursé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    policy = models.ForeignKey("policies.Policy", on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(max_length=20)
    amount = models.PositiveIntegerField(help_text="MRU")
    payer_phone = models.CharField(max_length=16, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    external_ref = models.CharField(max_length=80, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "external_ref"],
                condition=~models.Q(external_ref=""),
                name="unique_external_ref_per_provider",
            )
        ]


class Refund(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Demandé"
        DONE = "done", "Effectué"
        FAILED = "failed", "Échoué, à traiter à la main"

    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name="refund")
    amount = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)
    external_ref = models.CharField(max_length=80, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CallbackLog(models.Model):
    """Trace brute de chaque callback reçu, valide ou non, pour le rapprochement."""

    provider = models.CharField(max_length=20)
    received_at = models.DateTimeField(auto_now_add=True)
    signature_ok = models.BooleanField()
    body = models.TextField()
    outcome = models.CharField(max_length=80, blank=True)
