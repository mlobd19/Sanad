import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("En attente de confirmation")
        SUCCEEDED = "succeeded", _("Confirmé")
        FAILED = "failed", _("Échoué")
        REFUNDED = "refunded", _("Remboursé")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name=_("identifiant"))
    # Soit une police (particulier), soit une commande de plusieurs polices (entreprise).
    policy = models.ForeignKey("policies.Policy", null=True, blank=True, on_delete=models.PROTECT,
                               related_name="payments", verbose_name=_("police"))
    order = models.ForeignKey("policies.Order", null=True, blank=True, on_delete=models.PROTECT,
                              related_name="payments", verbose_name=_("commande"))
    provider = models.CharField(max_length=20, verbose_name=_("moyen de paiement"))
    amount = models.PositiveIntegerField(help_text=_("MRU"), verbose_name=_("montant (MRU)"))
    payer_phone = models.CharField(max_length=16, blank=True, verbose_name=_("numéro du payeur"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True, verbose_name=_("statut"))
    external_ref = models.CharField(max_length=80, blank=True, verbose_name=_("référence opérateur"))
    failure_reason = models.CharField(max_length=255, blank=True, verbose_name=_("motif de l'échec"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("créé le"))
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("confirmé le"))

    class Meta:
        verbose_name = _("paiement")
        verbose_name_plural = _("paiements")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "external_ref"],
                condition=~models.Q(external_ref=""),
                name="unique_external_ref_per_provider",
            ),
            models.CheckConstraint(
                condition=(models.Q(policy__isnull=False, order__isnull=True)
                           | models.Q(policy__isnull=True, order__isnull=False)),
                name="payment_for_policy_xor_order",
            ),
        ]

    @property
    def refunded_amount(self) -> int:
        return sum(r.amount for r in self.refunds.all())


class Refund(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", _("Demandé")
        DONE = "done", _("Effectué")
        FAILED = "failed", _("Échoué, à traiter à la main")

    # Plusieurs remboursements possibles : une commande peut être remboursée ligne par ligne.
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds", verbose_name=_("paiement"))
    policy = models.ForeignKey("policies.Policy", null=True, blank=True, on_delete=models.PROTECT,
                               related_name="refunds", verbose_name=_("police"))
    amount = models.PositiveIntegerField(verbose_name=_("montant (MRU)"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED, verbose_name=_("statut"))
    external_ref = models.CharField(max_length=80, blank=True, verbose_name=_("référence opérateur"))
    note = models.CharField(max_length=255, blank=True, verbose_name=_("note"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("créé le"))

    class Meta:
        verbose_name = _("remboursement")
        verbose_name_plural = _("remboursements")


class CallbackLog(models.Model):
    """Trace brute de chaque callback reçu, valide ou non, pour le rapprochement."""

    provider = models.CharField(max_length=20, verbose_name=_("opérateur"))
    received_at = models.DateTimeField(auto_now_add=True, verbose_name=_("reçu le"))
    signature_ok = models.BooleanField(verbose_name=_("signature valide"))
    body = models.TextField(verbose_name=_("contenu"))
    outcome = models.CharField(max_length=80, blank=True, verbose_name=_("résultat"))

    class Meta:
        verbose_name = _("callback opérateur")
        verbose_name_plural = _("callbacks opérateurs")
