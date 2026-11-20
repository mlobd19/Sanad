"""Espace entreprise : un compte distinct des comptes particuliers.

Une entreprise s'inscrit en ligne, dépose son NIF et son Registre du Commerce,
puis l'équipe Sanad la vérifie. Elle ne peut payer qu'une fois vérifiée.
"""
import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

NIF_RE = re.compile(r"^[A-Z0-9]{5,20}$")
RC_RE = re.compile(r"^[A-Z0-9][A-Z0-9 /.\-]{2,38}[A-Z0-9]$")


def normalize_identifier(raw: str) -> str:
    """NIF : majuscules, sans espaces ni séparateurs."""
    return re.sub(r"[\s\-./]", "", raw or "").upper()


class Company(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "En vérification"
        VERIFIED = "verified", "Vérifiée"
        REJECTED = "rejected", "Refusée"

    legal_name = models.CharField("raison sociale", max_length=200)
    nif = models.CharField("NIF", max_length=20, unique=True, help_text="Numéro d'identification fiscale.")
    rc_number = models.CharField("n° Registre du Commerce", max_length=40)
    address = models.CharField("adresse", max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    rejection_reason = models.CharField(
        "motif du refus", max_length=255, blank=True, help_text="Obligatoire pour refuser l'entreprise."
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "entreprise"

    def __str__(self):
        return self.legal_name

    def clean(self):
        self.nif = normalize_identifier(self.nif)
        self.rc_number = " ".join((self.rc_number or "").upper().split())  # mise en forme d'origine conservée
        if not NIF_RE.match(self.nif):
            raise ValidationError({"nif": "NIF invalide : 5 à 20 lettres ou chiffres."})
        if not RC_RE.match(self.rc_number):
            raise ValidationError({"rc_number": "N° de Registre du Commerce invalide (lettres, chiffres, / . -)."})

    @property
    def is_verified(self) -> bool:
        return self.status == self.Status.VERIFIED


def document_upload_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"companies/{instance.company_id}/{uuid.uuid4().hex}.{ext}"


class CompanyDocument(models.Model):
    class Kind(models.TextChoices):
        NIF = "nif", "Attestation NIF"
        RC = "rc", "Registre du Commerce"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=4, choices=Kind.choices)
    file = models.FileField(upload_to=document_upload_path)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "pièce de l'entreprise"


class Membership(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrateur"
        MANAGER = "manager", "Gestionnaire"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="memberships")
    # Un compte membre appartient à une seule entreprise.
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membership")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MANAGER)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "membre"

    def __str__(self):
        return f"{self.user} · {self.company} ({self.get_role_display()})"
