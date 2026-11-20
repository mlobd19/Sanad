import calendar
from datetime import date, timedelta

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.accounts.storage import PrivateStorage


def add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


class InsuredAsset(models.Model):
    """Bien assuré. Générique pour accueillir plus tard un logement ou un voyage."""

    class Kind(models.TextChoices):
        VEHICLE = "vehicle", _("Véhicule")

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assets", verbose_name=_("déclaré par"))
    # Flotte d'une entreprise : le bien appartient à l'entreprise ; owner = le membre qui l'a déclaré.
    company = models.ForeignKey("companies.Company", null=True, blank=True, on_delete=models.PROTECT,
                                related_name="assets", verbose_name=_("entreprise"))
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.VEHICLE, verbose_name=_("type"))
    reference = models.CharField(max_length=40, db_index=True, help_text=_("Immatriculation pour un véhicule."), verbose_name=_("immatriculation"))
    attributes = models.JSONField(default=dict, help_text=_("Marque, modèle, puissance fiscale, usage…"), verbose_name=_("caractéristiques"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("créé le"))

    class Meta:
        verbose_name = _("bien assuré")
        verbose_name_plural = _("biens assurés")

    def __str__(self):
        return f"{self.get_kind_display()} {self.reference}"


class Quote(models.Model):
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quotes", verbose_name=_("client"))
    asset = models.ForeignKey(InsuredAsset, on_delete=models.CASCADE, related_name="quotes", verbose_name=_("bien assuré"))
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="quotes", verbose_name=_("formule"))
    premium = models.PositiveIntegerField(help_text=_("MRU"), verbose_name=_("prime (MRU)"))
    duration_months = models.PositiveSmallIntegerField(default=12, verbose_name=_("durée (mois)"))
    tariff_version = models.CharField(max_length=20, verbose_name=_("version du tarif"))
    attributes_snapshot = models.JSONField(default=dict, verbose_name=_("caractéristiques au moment du devis"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("créé le"))
    expires_at = models.DateTimeField(verbose_name=_("expire le"))

    class Meta:
        verbose_name = _("devis")
        verbose_name_plural = _("devis")
        ordering = ["premium"]


class Order(models.Model):
    """Commande : plusieurs polices réglées par un seul paiement (flotte d'une entreprise)."""

    company = models.ForeignKey("companies.Company", null=True, blank=True, on_delete=models.PROTECT,
                                related_name="orders", verbose_name=_("entreprise"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders", verbose_name=_("commandée par"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("créée le"))

    class Meta:
        verbose_name_plural = _("commandes")
        ordering = ["-created_at"]
        verbose_name = _("commande")

    def __str__(self):
        return f"Commande #{self.pk}"

    @property
    def total(self) -> int:
        return sum(p.premium for p in self.policies.all())


class Policy(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("En attente de paiement")
        PAID = "paid", _("Payée, à valider par l'assureur")
        ACTIVE = "active", _("Active")
        REFUSED = "refused", _("Refusée (remboursée)")
        CANCELLED = "cancelled", _("Résiliée")
        EXPIRED = "expired", _("Expirée")

    quote = models.OneToOneField(Quote, on_delete=models.PROTECT, related_name="policy", verbose_name=_("devis"))
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="policies", verbose_name=_("client"))
    asset = models.ForeignKey(InsuredAsset, on_delete=models.PROTECT, related_name="policies", verbose_name=_("bien assuré"))
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="policies", verbose_name=_("formule"))
    premium = models.PositiveIntegerField(help_text=_("MRU"), verbose_name=_("prime (MRU)"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True, verbose_name=_("statut"))
    starts_on = models.DateField(verbose_name=_("début"))
    ends_on = models.DateField(verbose_name=_("fin"))
    insurer_reference = models.CharField(max_length=60, blank=True, help_text=_("N° de police chez l'assureur."), verbose_name=_("n° de police chez l'assureur"))
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("décidée par")
    )
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name=_("décidée le"))
    refusal_reason = models.CharField(max_length=255, blank=True, verbose_name=_("motif du refus"))
    renewal_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="renewals", verbose_name=_("renouvelle"))
    # Contrat d'entreprise : customer = le membre qui a souscrit, company = le titulaire.
    company = models.ForeignKey("companies.Company", null=True, blank=True, on_delete=models.PROTECT,
                                related_name="policies", verbose_name=_("entreprise"))
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.PROTECT, related_name="policies", verbose_name=_("commande"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("créée le"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("mise à jour le"))

    class Meta:
        verbose_name = _("police")
        ordering = ["-created_at"]
        verbose_name_plural = _("polices")

    def __str__(self):
        return f"Police #{self.pk} · {self.asset.reference} · {self.get_status_display()}"

    @property
    def insurer(self):
        return self.product.insurer

    @staticmethod
    def compute_end(starts_on: date, months: int) -> date:
        return add_months(starts_on, months) - timedelta(days=1)


class Claim(models.Model):
    """Sinistre déclaré par le client, traité par l'assureur dans son portail (ou par l'équipe Sanad)."""

    class Kind(models.TextChoices):
        ACCIDENT = "accident", _("Accident")
        THEFT = "theft", _("Vol")
        FIRE = "fire", _("Incendie")
        GLASS = "glass", _("Bris de glace")
        OTHER = "other", _("Autre")

    class Status(models.TextChoices):
        SUBMITTED = "submitted", _("Déclaré")
        IN_REVIEW = "in_review", _("En cours chez l'assureur")
        CLOSED = "closed", _("Clos")

    policy = models.ForeignKey(Policy, on_delete=models.PROTECT, related_name="claims", verbose_name=_("police"))
    declared_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+",
                                    verbose_name=_("déclaré par"))
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.ACCIDENT, verbose_name=_("type"))
    occurred_on = models.DateField(verbose_name=_("date du sinistre"))
    place = models.CharField(max_length=200, default="", verbose_name=_("lieu"))
    description = models.TextField(verbose_name=_("description"))
    third_party_plate = models.CharField(max_length=40, blank=True, verbose_name=_("immatriculation du tiers"))
    injuries = models.BooleanField(default=False, verbose_name=_("blessés"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUBMITTED, db_index=True,
                              verbose_name=_("statut"))
    closing_note = models.CharField(max_length=500, blank=True, verbose_name=_("note de clôture"))
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+", verbose_name=_("traité par"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("déclaré le"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("mis à jour le"))

    class Meta:
        verbose_name = _("sinistre")
        verbose_name_plural = _("sinistres")
        ordering = ["-created_at"]

    def __str__(self):
        return self.number

    @property
    def number(self) -> str:
        """Numéro communiqué au client et à l'assureur : SIN-AAAA-NNNNNN."""
        return f"SIN-{self.created_at:%Y}-{self.pk:06d}" if self.pk and self.created_at else "SIN-?"


def claim_upload_path(instance, filename):
    import uuid

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"claims/{instance.claim_id}/{uuid.uuid4().hex}.{ext}"


class ClaimPhoto(models.Model):
    """Photo des dégâts ou constat amiable. Fichier privé : jamais d'URL publique."""

    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="photos", verbose_name=_("sinistre"))
    file = models.FileField(upload_to=claim_upload_path, storage=PrivateStorage(), verbose_name=_("photo"))
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("ajoutée le"))

    class Meta:
        verbose_name = _("photo de sinistre")
        verbose_name_plural = _("photos de sinistre")
        ordering = ["pk"]


class Commission(models.Model):
    policy = models.OneToOneField(Policy, on_delete=models.PROTECT, related_name="commission", verbose_name=_("police"))
    insurer = models.ForeignKey("catalog.Insurer", on_delete=models.PROTECT, related_name="commissions", verbose_name=_("compagnie"))
    rate = models.DecimalField(max_digits=5, decimal_places=4, verbose_name=_("taux"))
    amount = models.PositiveIntegerField(help_text=_("MRU"), verbose_name=_("montant (MRU)"))
    period = models.CharField(max_length=7, db_index=True, help_text=_("Mois du relevé, AAAA-MM."), verbose_name=_("mois"))
    is_paid = models.BooleanField(default=False, verbose_name=_("payée"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("créée le"))

    class Meta:
        verbose_name = _("commission")
        verbose_name_plural = _("commissions")
