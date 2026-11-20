import calendar
from datetime import date, timedelta

from django.conf import settings
from django.db import models


def add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


class InsuredAsset(models.Model):
    """Bien assuré. Générique pour accueillir plus tard un logement ou un voyage."""

    class Kind(models.TextChoices):
        VEHICLE = "vehicle", "Véhicule"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assets")
    # Flotte d'une entreprise : le bien appartient à l'entreprise ; owner = le membre qui l'a déclaré.
    company = models.ForeignKey("companies.Company", null=True, blank=True, on_delete=models.PROTECT,
                                related_name="assets")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.VEHICLE)
    reference = models.CharField(max_length=40, db_index=True, help_text="Immatriculation pour un véhicule.")
    attributes = models.JSONField(default=dict, help_text="Marque, modèle, puissance fiscale, usage…")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_kind_display()} {self.reference}"


class Quote(models.Model):
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quotes")
    asset = models.ForeignKey(InsuredAsset, on_delete=models.CASCADE, related_name="quotes")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="quotes")
    premium = models.PositiveIntegerField(help_text="MRU")
    tariff_version = models.CharField(max_length=20)
    attributes_snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["premium"]


class Order(models.Model):
    """Commande : plusieurs polices réglées par un seul paiement (flotte d'une entreprise)."""

    company = models.ForeignKey("companies.Company", null=True, blank=True, on_delete=models.PROTECT,
                                related_name="orders")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "commande"

    def __str__(self):
        return f"Commande #{self.pk}"

    @property
    def total(self) -> int:
        return sum(p.premium for p in self.policies.all())


class Policy(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "En attente de paiement"
        PAID = "paid", "Payée, à valider par l'assureur"
        ACTIVE = "active", "Active"
        REFUSED = "refused", "Refusée (remboursée)"
        CANCELLED = "cancelled", "Résiliée"
        EXPIRED = "expired", "Expirée"

    quote = models.OneToOneField(Quote, on_delete=models.PROTECT, related_name="policy")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="policies")
    asset = models.ForeignKey(InsuredAsset, on_delete=models.PROTECT, related_name="policies")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="policies")
    premium = models.PositiveIntegerField(help_text="MRU")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    starts_on = models.DateField()
    ends_on = models.DateField()
    insurer_reference = models.CharField(max_length=60, blank=True, help_text="N° de police chez l'assureur.")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    refusal_reason = models.CharField(max_length=255, blank=True)
    renewal_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="renewals")
    # Contrat d'entreprise : customer = le membre qui a souscrit, company = le titulaire.
    company = models.ForeignKey("companies.Company", null=True, blank=True, on_delete=models.PROTECT,
                                related_name="policies")
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.PROTECT, related_name="policies")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "policies"

    def __str__(self):
        return f"Police #{self.pk} · {self.asset.reference} · {self.get_status_display()}"

    @property
    def insurer(self):
        return self.product.insurer

    @staticmethod
    def compute_end(starts_on: date, months: int) -> date:
        return add_months(starts_on, months) - timedelta(days=1)


class Claim(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Déclaré"
        SENT = "sent", "Transmis à l'assureur"
        IN_REVIEW = "in_review", "En cours chez l'assureur"
        CLOSED = "closed", "Clos"

    policy = models.ForeignKey(Policy, on_delete=models.PROTECT, related_name="claims")
    occurred_on = models.DateField()
    description = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUBMITTED)
    created_at = models.DateTimeField(auto_now_add=True)


def claim_upload_path(instance, filename):
    import uuid

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"claims/{instance.claim_id}/{uuid.uuid4().hex}.{ext}"


class ClaimPhoto(models.Model):
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="photos")
    file = models.FileField(upload_to=claim_upload_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)


class Commission(models.Model):
    policy = models.OneToOneField(Policy, on_delete=models.PROTECT, related_name="commission")
    insurer = models.ForeignKey("catalog.Insurer", on_delete=models.PROTECT, related_name="commissions")
    rate = models.DecimalField(max_digits=5, decimal_places=4)
    amount = models.PositiveIntegerField(help_text="MRU")
    period = models.CharField(max_length=7, db_index=True, help_text="Mois du relevé, AAAA-MM.")
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
