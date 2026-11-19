from django.contrib import admin

from .models import Attestation


@admin.register(Attestation)
class AttestationAdmin(admin.ModelAdmin):
    list_display = ("number", "policy", "status", "issued_at", "revoked_at")
    list_filter = ("status",)
    search_fields = ("number", "payload")
    readonly_fields = ("policy", "number", "payload", "token", "issued_at", "revoked_at", "revoked_reason", "status")
