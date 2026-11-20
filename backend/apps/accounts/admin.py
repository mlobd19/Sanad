from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.audit.models import record

from .models import KycDocument, User
from .services import send_password_email


class KycDocumentInline(admin.TabularInline):
    model = KycDocument
    fk_name = "user"
    extra = 0
    fields = ("kind", "file", "status", "review_note", "uploaded_at")
    readonly_fields = ("uploaded_at",)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-date_joined",)
    list_display = ("phone", "email", "full_name", "role", "insurer", "kyc_status", "date_joined")
    list_filter = ("role", "kyc_status", "insurer")
    search_fields = ("phone", "email", "full_name", "nni")
    inlines = [KycDocumentInline]
    fieldsets = (
        (None, {"fields": ("phone", "email", "password")}),
        ("Sécurité", {"fields": ("failed_logins", "locked_until", "last_login")}),
        ("Identité", {"fields": ("full_name", "nni", "language", "kyc_status")}),
        ("Rôle", {"fields": ("role", "insurer", "is_active", "is_staff", "is_superuser", "groups")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("phone", "email", "password1", "password2", "role", "insurer")}),)
    readonly_fields = ("last_login",)
    actions = ["mark_kyc_verified", "send_invitation"]

    @admin.action(description="Marquer le KYC comme vérifié")
    def mark_kyc_verified(self, request, queryset):
        for user in queryset:
            user.kyc_status = User.KycStatus.VERIFIED
            user.save(update_fields=["kyc_status"])
            user.documents.filter(status=KycDocument.Status.PENDING).update(
                status=KycDocument.Status.ACCEPTED, reviewed_by=request.user
            )
            record("kyc.verified", user, actor=request.user)

    @admin.action(description="Envoyer l'invitation par email (choix du mot de passe)")
    def send_invitation(self, request, queryset):
        sent = 0
        for user in queryset:
            if not user.is_pro:
                self.message_user(request, f"{user} : pas un compte professionnel, ignoré.", messages.WARNING)
                continue
            try:
                send_password_email(user, "invite", actor=request.user)
                sent += 1
            except ValidationError as exc:
                self.message_user(request, f"{user} : {exc.messages[0]}", messages.ERROR)
        if sent:
            self.message_user(request, f"Invitation envoyée à {sent} compte(s).", messages.SUCCESS)
