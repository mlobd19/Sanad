from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.backoffice.ui import status_pill

from .models import Attestation


@admin.register(Attestation)
class AttestationAdmin(admin.ModelAdmin):
    """Consultation seule : une attestation se révoque en résiliant la police."""

    list_display = ("number", "policy", "status_display", "issued_at", "revoked_at")
    list_filter = ("status",)
    search_fields = ("number", "policy__asset__reference")
    date_hierarchy = "issued_at"
    readonly_fields = ("policy", "number", "status", "issued_at", "revoked_at", "revoked_reason", "payload", "token")
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description=_("statut"), ordering="status")
    def status_display(self, att):
        return status_pill(att)
