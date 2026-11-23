from django.contrib import admin

from .models import NotificationFailure


@admin.register(NotificationFailure)
class NotificationFailureAdmin(admin.ModelAdmin):
    """Envois en échec (lecture seule) : l'équipe en est prévenue par e-mail toutes les 15 min."""

    list_display = ("created_at", "channel", "template", "recipient", "error")
    list_filter = ("channel", "template")
    readonly_fields = ("created_at", "channel", "template", "recipient", "error")
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
