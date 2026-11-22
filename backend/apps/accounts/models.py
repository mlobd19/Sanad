import re
import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .storage import PrivateStorage

PHONE_RE = re.compile(r"^\+222\d{8}$")


def format_phone(value: str) -> str:
    """Affichage : « +22236000001 » → « +222 36 00 00 01 » (autre format : inchangé)."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 11 and digits.startswith("222"):
        local = digits[3:]
        return "+222 " + " ".join(local[i:i + 2] for i in range(0, 8, 2))
    return value or ""


def normalize_phone(raw: str) -> str:
    """Ramène un numéro mauritanien à la forme +222XXXXXXXX."""
    digits = re.sub(r"[^\d+]", "", raw or "")
    if digits.startswith("00222"):
        digits = "+" + digits[2:]
    elif digits.startswith("222") and len(digits) == 11:
        digits = "+" + digits
    elif len(digits) == 8 and digits.isdigit():
        digits = "+222" + digits
    if not PHONE_RE.match(digits):
        raise ValidationError("Numéro de téléphone mauritanien invalide.")
    return digits


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, phone, password=None, **extra):
        user = self.model(phone=normalize_phone(phone), **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def get_by_natural_key(self, phone):
        # Le numéro n'identifie qu'un compte particulier (ou d'équipe), jamais un compte pro.
        return self.exclude(role__in=User.PRO_ROLES).get(phone=normalize_phone(phone))

    def create_superuser(self, phone, password, **extra):
        extra.update(is_staff=True, is_superuser=True, role=User.Role.STAFF)
        return self.create_user(phone, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        CUSTOMER = "customer", _("Client")
        INSURER_AGENT = "insurer_agent", _("Agent assureur")
        COMPANY_MEMBER = "company_member", _("Membre d'une entreprise")
        STAFF = "staff", _("Équipe interne")

    class KycStatus(models.TextChoices):
        NONE = "none", _("Non commencé")
        PENDING = "pending", _("En vérification")
        VERIFIED = "verified", _("Vérifié")
        REJECTED = "rejected", _("Refusé")

    # Un numéro = un seul compte particulier. Le même numéro peut aussi servir de second
    # facteur (SMS) à des comptes professionnels, identifiés eux par leur email.
    phone = models.CharField(max_length=16, db_index=True, verbose_name=_("téléphone"))
    email = models.EmailField(
        _("email professionnel"), null=True, blank=True, unique=True,
        help_text=_("Identifiant des comptes professionnels (agents assureurs), avec mot de passe et code SMS."),
    )
    full_name = models.CharField(max_length=120, blank=True, verbose_name=_("nom complet"))
    nni = models.CharField(_("NNI"), max_length=20, blank=True, db_index=True)
    language = models.CharField(max_length=2, choices=[("fr", "Français"), ("ar", "العربية")], default="fr", verbose_name=_("langue"))
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER, verbose_name=_("rôle"))
    insurer = models.ForeignKey(
        "catalog.Insurer", null=True, blank=True, on_delete=models.PROTECT, related_name="agents",
        help_text=_("Renseigné uniquement pour les agents assureurs."), verbose_name=_("compagnie d'assurance"),
    )
    kyc_status = models.CharField(max_length=10, choices=KycStatus.choices, default=KycStatus.NONE, verbose_name=_("vérification d'identité"))
    is_active = models.BooleanField(default=True, verbose_name=_("actif"))
    is_staff = models.BooleanField(default=False, verbose_name=_("accès au back-office"))
    date_joined = models.DateTimeField(default=timezone.now, verbose_name=_("inscrit le"))
    # Protection du mot de passe des comptes professionnels.
    failed_logins = models.PositiveSmallIntegerField(default=0, verbose_name=_("échecs de connexion"))
    locked_until = models.DateTimeField(null=True, blank=True, verbose_name=_("bloqué jusqu'au"))

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    # Rôles qui se connectent par email + mot de passe + code SMS (jamais par SMS seul).
    PRO_ROLES = (Role.INSURER_AGENT, Role.COMPANY_MEMBER)

    class Meta:
        verbose_name = _("compte")
        verbose_name_plural = _("comptes")
        constraints = [
            models.UniqueConstraint(
                fields=["phone"],
                condition=~models.Q(role__in=["insurer_agent", "company_member"]),
                name="unique_phone_personal_account",
                violation_error_message="Un compte existe déjà avec ce numéro.",
            )
        ]

    @property
    def is_pro(self) -> bool:
        return self.role in self.PRO_ROLES

    def clean(self):
        if self.role == self.Role.INSURER_AGENT and not self.insurer_id:
            raise ValidationError("Un agent assureur doit être rattaché à un assureur.")
        if self.is_pro and not self.email:
            raise ValidationError("Un compte professionnel doit avoir un email.")

    def set_password(self, raw_password):
        super().set_password(raw_password)
        self._password_changed = True

    def save(self, *args, **kwargs):
        # Un email vide devient NULL (sinon deux comptes sans email violeraient l'unicité).
        self.email = (self.email or "").strip().lower() or None
        super().save(*args, **kwargs)
        # Nouveau mot de passe (changement, réinitialisation, back-office…) : toutes les connexions
        # ouvertes avec l'ancien sont fermées, sur tous les appareils.
        if getattr(self, "_password_changed", False):
            self._password_changed = False
            AuthToken.objects.filter(user=self).delete()

    def __str__(self):
        return self.full_name or self.phone

    def get_short_name(self):
        return self.full_name or self.phone


class OtpCode(models.Model):
    class Purpose(models.TextChoices):
        CUSTOMER = "customer", _("Connexion particulier")
        PRO = "pro", _("Connexion compte professionnel")
        SIGNUP = "signup", _("Inscription entreprise")
        STAFF = "staff", _("Connexion back-office")

    phone = models.CharField(max_length=16, db_index=True)
    # Un code ne sert qu'au parcours qui l'a demandé (le même numéro peut porter plusieurs comptes).
    purpose = models.CharField(max_length=10, choices=Purpose.choices, default=Purpose.CUSTOMER)
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]


def kyc_upload_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"kyc/{instance.user_id}/{uuid.uuid4().hex}.{ext}"


class KycDocument(models.Model):
    class Kind(models.TextChoices):
        ID_CARD = "id_card", _("Carte d'identité")
        PASSPORT = "passport", _("Passeport")
        VEHICLE_REGISTRATION = "vehicle_registration", _("Carte grise")

    class Status(models.TextChoices):
        PENDING = "pending", _("À vérifier")
        ACCEPTED = "accepted", _("Accepté")
        REJECTED = "rejected", _("Refusé")

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="documents", verbose_name=_("compte"))
    kind = models.CharField(max_length=24, choices=Kind.choices, verbose_name=_("type de pièce"))
    file = models.FileField(upload_to=kyc_upload_path, storage=PrivateStorage(), verbose_name=_("fichier"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, verbose_name=_("statut"))
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("vérifiée par"))
    review_note = models.CharField(max_length=255, blank=True, verbose_name=_("note de vérification"))
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("déposée le"))

    class Meta:
        verbose_name = _("pièce d'identité")
        verbose_name_plural = _("pièces d'identité")
        ordering = ["-uploaded_at"]


class IdentityCheck(models.Model):
    """Une interrogation du registre national (ANRPTS ou simulateur). Journal, jamais modifié."""

    class Outcome(models.TextChoices):
        MATCH = "match", _("Identité confirmée")
        MISMATCH = "mismatch", _("Nom différent du registre")
        NOT_FOUND = "not_found", _("NNI inconnu du registre")
        UNAVAILABLE = "unavailable", _("Registre injoignable")

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="identity_checks", verbose_name=_("compte"))
    provider = models.CharField(max_length=20, verbose_name=_("source"))
    nni = models.CharField(_("NNI"), max_length=20)
    full_name = models.CharField(max_length=120, verbose_name=_("nom complet"))
    outcome = models.CharField(max_length=12, choices=Outcome.choices, verbose_name=_("résultat"))
    reference = models.CharField(max_length=64, blank=True, verbose_name=_("référence du registre"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("vérifiée le"))

    class Meta:
        verbose_name = _("vérification au registre national")
        verbose_name_plural = _("vérifications au registre national")
        ordering = ["-created_at"]


class AuthToken(models.Model):
    """Connexion d'un appareil à l'app (un jeton par appareil), à durée de vie limitée.

    Seule l'empreinte SHA-256 du jeton est enregistrée : une fuite de la base ne donne accès à aucun compte.
    Durée : 30 jours pour un particulier, 8 h pour un compte professionnel (accounts/tokens.py).
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="auth_tokens", verbose_name=_("compte"))
    digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("ouverte le"))
    expires_at = models.DateTimeField(db_index=True, verbose_name=_("expire le"))
    last_used_at = models.DateTimeField(null=True, blank=True, verbose_name=_("dernière utilisation"))
    user_agent = models.CharField(max_length=200, blank=True, verbose_name=_("appareil"))

    class Meta:
        verbose_name = _("connexion")
        verbose_name_plural = _("connexions")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} · {self.created_at:%Y-%m-%d %H:%M}"


class TotpDevice(models.Model):
    """Application d'authentification (TOTP) d'un compte équipe : second facteur du back-office."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="totp", verbose_name=_("compte"))
    secret = models.CharField(max_length=64)
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("activée le"))
    # Dernier pas de 30 s accepté : un même code ne sert jamais deux fois.
    last_step = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("application d'authentification")
        verbose_name_plural = _("applications d'authentification")
