from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

LOGO_EXTENSIONS = ["png", "jpg", "jpeg", "webp"]  # pas de SVG : il peut embarquer du script


def logo_upload_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"insurers/{instance.slug}.{ext}"


class Insurer(models.Model):
    class Integration(models.TextChoices):
        PORTAL = "portal", "Portail assureur"
        FILE = "file", "Export fichier"
        API = "api", "API temps réel"

    name = models.CharField(max_length=120, unique=True, help_text="Nom court affiché, ex. NASR.")
    legal_name = models.CharField(max_length=200, blank=True, help_text="Raison sociale complète.")
    slug = models.SlugField(unique=True)
    logo = models.ImageField(
        upload_to=logo_upload_path, blank=True,
        validators=[FileExtensionValidator(LOGO_EXTENSIONS)],
        help_text="Logo officiel fourni par la compagnie (PNG, JPG ou WebP, fond clair de préférence).",
    )
    contact_email = models.EmailField(blank=True)
    integration = models.CharField(max_length=10, choices=Integration.choices, default=Integration.PORTAL)
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=4, help_text="Ex. 0.1500 pour 15 % (selon le contrat de partenariat)."
    )
    auto_validate = models.BooleanField(
        default=False, help_text="Si vrai, la police est activée dès le paiement confirmé (assureurs en API)."
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    class Branch(models.TextChoices):
        AUTO = "auto", "Automobile"
        HEALTH = "health", "Santé"
        HOME = "home", "Habitation"
        TRAVEL = "travel", "Voyage"
        TAKAFUL = "takaful", "Takaful"

    insurer = models.ForeignKey(Insurer, on_delete=models.PROTECT, related_name="products")
    branch = models.CharField(max_length=10, choices=Branch.choices, default=Branch.AUTO)
    code = models.SlugField()
    name = models.CharField(max_length=120, help_text="Ex. RC seule, Tiers étendu, Tous risques.")
    coverages = models.JSONField(default=list, help_text="Liste des garanties affichées au client.")
    base_premium = models.PositiveIntegerField(help_text="Prime annuelle de base en MRU.")
    duration_months = models.PositiveSmallIntegerField(default=12)
    tariff_version = models.CharField(max_length=20, default="v1")
    is_indicative = models.BooleanField(
        default=False, help_text="Tarif indicatif (démo) : pas encore la grille officielle de l'assureur."
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("insurer", "code")]
        ordering = ["insurer__name", "base_premium"]

    def __str__(self):
        return f"{self.insurer} · {self.name}"

    def price(self, attributes: dict) -> int:
        """Prime en MRU : base × multiplicateurs des facteurs applicables."""
        premium = Decimal(self.base_premium)
        for factor in self.factors.all():
            if factor.applies_to(attributes):
                premium *= factor.multiplier
        return int(premium.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class TariffFactor(models.Model):
    """Une ligne de la grille tarifaire importée de l'assureur."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="factors")
    attribute = models.CharField(max_length=40, help_text="Attribut du bien, ex. fiscal_power, usage, age_years.")
    equals = models.CharField(max_length=40, blank=True, help_text="Valeur exacte (attributs texte).")
    min_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    multiplier = models.DecimalField(max_digits=6, decimal_places=4)

    def clean(self):
        if not self.equals and self.min_value is None and self.max_value is None:
            raise ValidationError("Renseigner une valeur exacte ou une plage.")

    def applies_to(self, attributes: dict) -> bool:
        if self.attribute not in attributes:
            return False
        value = attributes[self.attribute]
        if self.equals:
            return str(value) == self.equals
        try:
            number = Decimal(str(value))
        except Exception:
            return False
        if self.min_value is not None and number < self.min_value:
            return False
        if self.max_value is not None and number > self.max_value:
            return False
        return True
