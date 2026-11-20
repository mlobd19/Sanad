from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from . import services
from .models import Company, CompanyDocument, Membership


class DocumentInline(admin.TabularInline):
    model = CompanyDocument
    extra = 0
    fields = ("kind", "file", "uploaded_by", "uploaded_at")
    readonly_fields = ("uploaded_by", "uploaded_at")


class MembershipInline(admin.TabularInline):
    model = Membership
    fk_name = "company"
    extra = 0
    fields = ("user", "role", "invited_by", "created_at")
    readonly_fields = ("invited_by", "created_at")
    raw_id_fields = ("user",)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("legal_name", "nif", "rc_number", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("legal_name", "nif", "rc_number")
    readonly_fields = ("status", "verified_by", "verified_at", "created_at")
    fields = ("legal_name", "nif", "rc_number", "address", "status", "rejection_reason", "verified_by",
              "verified_at", "created_at")
    inlines = [DocumentInline, MembershipInline]
    actions = ["verify", "reject"]

    @admin.action(description="Vérifier l'entreprise (NIF et RC contrôlés)")
    def verify(self, request, queryset):
        for company in queryset:
            try:
                services.verify_company(company, request.user)
                self.message_user(request, f"{company} : vérifiée.", messages.SUCCESS)
            except ValidationError as exc:
                self.message_user(request, f"{company} : {exc.messages[0]}", messages.ERROR)

    @admin.action(description="Refuser l'entreprise (motif saisi dans sa fiche)")
    def reject(self, request, queryset):
        for company in queryset:
            try:
                services.reject_company(company, request.user, company.rejection_reason)
                self.message_user(request, f"{company} : refusée.", messages.WARNING)
            except ValidationError as exc:
                self.message_user(request, f"{company} : {exc.messages[0]} Renseignez-le dans la fiche.",
                                  messages.ERROR)
