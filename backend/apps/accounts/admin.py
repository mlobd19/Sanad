from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.audit.models import record

from .models import KycDocument, User


class KycDocumentInline(admin.TabularInline):
    model = KycDocument
    fk_name = "user"
    extra = 0
    fields = ("kind", "file", "status", "review_note", "uploaded_at")
    readonly_fields = ("uploaded_at",)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-date_joined",)
    list_display = ("phone", "full_name", "role", "insurer", "kyc_status", "date_joined")
    list_filter = ("role", "kyc_status", "insurer")
    search_fields = ("phone", "full_name", "nni")
    inlines = [KycDocumentInline]
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Identité", {"fields": ("full_name", "nni", "language", "kyc_status")}),
        ("Rôle", {"fields": ("role", "insurer", "is_active", "is_staff", "is_superuser", "groups")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("phone", "password1", "password2", "role", "insurer")}),)
    actions = ["mark_kyc_verified"]

    @admin.action(description="Marquer le KYC comme vérifié")
    def mark_kyc_verified(self, request, queryset):
        for user in queryset:
            user.kyc_status = User.KycStatus.VERIFIED
            user.save(update_fields=["kyc_status"])
            user.documents.filter(status=KycDocument.Status.PENDING).update(
                status=KycDocument.Status.ACCEPTED, reviewed_by=request.user
            )
            record("kyc.verified", user, actor=request.user)
