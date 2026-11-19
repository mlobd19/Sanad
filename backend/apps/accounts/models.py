import re
import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

PHONE_RE = re.compile(r"^\+222\d{8}$")


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

    def create_superuser(self, phone, password, **extra):
        extra.update(is_staff=True, is_superuser=True, role=User.Role.STAFF)
        return self.create_user(phone, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Client"
        INSURER_AGENT = "insurer_agent", "Agent assureur"
        STAFF = "staff", "Équipe interne"

    class KycStatus(models.TextChoices):
        NONE = "none", "Non commencé"
        PENDING = "pending", "En vérification"
        VERIFIED = "verified", "Vérifié"
        REJECTED = "rejected", "Refusé"

    phone = models.CharField(max_length=16, unique=True)
    full_name = models.CharField(max_length=120, blank=True)
    nni = models.CharField("NNI", max_length=20, blank=True, db_index=True)
    language = models.CharField(max_length=2, choices=[("fr", "Français"), ("ar", "العربية")], default="fr")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    insurer = models.ForeignKey(
        "catalog.Insurer", null=True, blank=True, on_delete=models.PROTECT, related_name="agents",
        help_text="Renseigné uniquement pour les agents assureurs.",
    )
    kyc_status = models.CharField(max_length=10, choices=KycStatus.choices, default=KycStatus.NONE)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    def clean(self):
        if self.role == self.Role.INSURER_AGENT and not self.insurer_id:
            raise ValidationError("Un agent assureur doit être rattaché à un assureur.")

    def __str__(self):
        return self.full_name or self.phone


class OtpCode(models.Model):
    phone = models.CharField(max_length=16, db_index=True)
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
        ID_CARD = "id_card", "Carte d'identité"
        PASSPORT = "passport", "Passeport"
        VEHICLE_REGISTRATION = "vehicle_registration", "Carte grise"

    class Status(models.TextChoices):
        PENDING = "pending", "À vérifier"
        ACCEPTED = "accepted", "Accepté"
        REJECTED = "rejected", "Refusé"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    file = models.FileField(upload_to=kyc_upload_path)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    review_note = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
