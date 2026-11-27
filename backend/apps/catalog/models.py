from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

LOGO_EXTENSIONS = ["png", "jpg", "jpeg", "webp"]  # pas de SVG : il peut embarquer du script

# Durées proposées (mois) et part de la prime annuelle facturée pour chacune.
# Barème court terme INDICATIF : à remplacer par le barème officiel (homologué
# pour la RC) dès qu'il est communiqué par les compagnies.
DURATIONS = (3, 6, 12)
DEFAULT_DURATION = 12
SHORT_TERM_RATES = {3: Decimal("0.40"), 6: Decimal("0.65"), 12: Decimal("1")}

# Voyage : durée possible et plafond minimal des frais médicaux, en euros. 30 000 € : l'attestation
# sert aussi aux demandes de visa Schengen, qui exigent au moins ce montant.
TRAVEL_MAX_DAYS = 92
TRAVEL_MIN_MEDICAL_EUR = 30_000
# Garanties voyage comparées (plafonds en euros dans Product.limits ; null = frais réels).
TRAVEL_LIMITS = ("medical", "repatriation", "baggage", "delay", "liability")


def logo_upload_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"insurers/{instance.slug}.{ext}"


class Insurer(models.Model):
    class Integration(models.TextChoices):
        PORTAL = "portal", _("Portail assureur")
        FILE = "file", _("Export fichier")
        API = "api", _("API temps réel")

    name = models.CharField(max_length=120, unique=True, help_text=_("Nom court affiché, ex. NASR."), verbose_name=_("nom"))
    legal_name = models.CharField(max_length=200, blank=True, help_text=_("Raison sociale complète."), verbose_name=_("raison sociale"))
    slug = models.SlugField(unique=True, verbose_name=_("code"))
    logo = models.ImageField(
        upload_to=logo_upload_path, blank=True,
        validators=[FileExtensionValidator(LOGO_EXTENSIONS)],
        help_text=_("Logo officiel fourni par la compagnie (PNG, JPG ou WebP, fond clair de préférence)."), verbose_name=_("logo"),
    )
    contact_email = models.EmailField(blank=True, verbose_name=_("email de contact"))
    assistance_phone = models.CharField(
        max_length=30, blank=True, help_text=_("Assistance 24 h/24 (voyage), imprimée sur l'attestation."),
        verbose_name=_("assistance 24 h/24"),
    )
    integration = models.CharField(max_length=10, choices=Integration.choices, default=Integration.PORTAL, verbose_name=_("intégration"))
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=4, help_text=_("Ex. 0.1500 pour 15 % (selon le contrat de partenariat)."), verbose_name=_("taux de commission")
    )
    auto_validate = models.BooleanField(
        default=False, help_text=_("Si vrai, la police est activée dès le paiement confirmé (assureurs en API)."), verbose_name=_("validation automatique")
    )
    is_active = models.BooleanField(default=True, verbose_name=_("active"))

    class Meta:
        verbose_name = _("compagnie d'assurance")
        verbose_name_plural = _("compagnies d'assurance")

    def __str__(self):
        return self.name


class Product(models.Model):
    class Branch(models.TextChoices):
        AUTO = "auto", _("Automobile")
        HEALTH = "health", _("Santé")
        HOME = "home", _("Habitation")
        TRAVEL = "travel", _("Voyage")
        TAKAFUL = "takaful", _("Takaful")

    insurer = models.ForeignKey(Insurer, on_delete=models.PROTECT, related_name="products", verbose_name=_("compagnie"))
    branch = models.CharField(max_length=10, choices=Branch.choices, default=Branch.AUTO, verbose_name=_("branche"))
    code = models.SlugField(verbose_name=_("code"))
    name = models.CharField(max_length=120, help_text=_("Ex. RC seule, Tiers étendu, Tous risques."), verbose_name=_("nom"))
    coverages = models.JSONField(default=list, help_text=_("Liste des garanties affichées au client."), verbose_name=_("garanties"))
    limits = models.JSONField(
        default=dict, blank=True,
        help_text=_("Voyage : plafonds en euros (medical, repatriation, baggage, delay, liability ; null = frais réels)."),
        verbose_name=_("plafonds"),
    )
    base_premium = models.PositiveIntegerField(
        help_text=_("Auto : prime annuelle de base. Voyage : prime d'un voyageur de 16 à 65 ans pour 1 à 8 jours. En MRU."),
        verbose_name=_("prime de base (MRU)"),
    )
    tariff_version = models.CharField(max_length=20, default="v1", verbose_name=_("version du tarif"))
    is_indicative = models.BooleanField(
        default=False, help_text=_("Tarif indicatif (démo) : pas encore la grille officielle de l'assureur."), verbose_name=_("tarif indicatif")
    )
    is_active = models.BooleanField(default=True, verbose_name=_("active"))

    class Meta:
        verbose_name = _("formule")
        verbose_name_plural = _("formules")
        unique_together = [("insurer", "code")]
        ordering = ["insurer__name", "base_premium"]

    def __str__(self):
        return f"{self.insurer} · {self.name}"

    def clean(self):
        if self.branch == self.Branch.TRAVEL and not self.meets_travel_minimum():
            raise ValidationError({"limits": _("Frais médicaux : 30 000 € au moins (visa Schengen).")})

    def meets_travel_minimum(self) -> bool:
        """Offre voyage : plafond des frais médicaux d'au moins 30 000 € (null = frais réels, sans plafond)."""
        limits = self.limits or {}
        if "medical" not in limits:
            return False
        medical = limits["medical"]
        return medical is None or (isinstance(medical, (int, float)) and medical >= TRAVEL_MIN_MEDICAL_EUR)

    def travel_premiums(self, days: int, ages: list[int]) -> list[int]:
        """Voyage : prime de chaque voyageur (MRU) = base × facteur de durée (trip_days) × facteur d'âge (age)."""
        if not 1 <= days <= TRAVEL_MAX_DAYS:
            raise ValidationError(f"Durée de voyage non proposée : {days} jours.")
        factors = list(self.factors.all())
        premiums = []
        for age in ages:
            premium = Decimal(self.base_premium)
            for factor in factors:
                if factor.applies_to({"trip_days": days, "age": age}):
                    premium *= factor.multiplier
            premiums.append(int(premium.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))
        return premiums

    def price(self, attributes: dict, months: int = DEFAULT_DURATION) -> int:
        """Prime en MRU : base annuelle × multiplicateurs des facteurs applicables × barème de durée."""
        if months not in SHORT_TERM_RATES:
            raise ValidationError(f"Durée non proposée : {months} mois.")
        premium = Decimal(self.base_premium) * SHORT_TERM_RATES[months]
        for factor in self.factors.all():
            if factor.applies_to(attributes):
                premium *= factor.multiplier
        return int(premium.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class TariffFactor(models.Model):
    """Une ligne de la grille tarifaire importée de l'assureur."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="factors", verbose_name=_("formule"))
    attribute = models.CharField(max_length=40, help_text=_("Attribut du bien, ex. fiscal_power, usage ; voyage : trip_days, age."), verbose_name=_("attribut"))
    equals = models.CharField(max_length=40, blank=True, help_text=_("Valeur exacte (attributs texte)."), verbose_name=_("valeur exacte"))
    min_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name=_("minimum"))
    max_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name=_("maximum"))
    multiplier = models.DecimalField(max_digits=6, decimal_places=4, verbose_name=_("coefficient"))

    class Meta:
        verbose_name = _("facteur tarifaire")
        verbose_name_plural = _("facteurs tarifaires")

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
