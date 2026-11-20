from django.contrib import admin

from .models import CallbackLog, Payment, Refund


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "policy", "order", "provider", "amount", "status", "external_ref", "created_at")
    list_filter = ("provider", "status")
    search_fields = ("external_ref", "payer_phone")
    readonly_fields = [f.name for f in Payment._meta.fields]


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("payment", "policy", "amount", "status", "external_ref", "created_at")
    list_filter = ("status",)


@admin.register(CallbackLog)
class CallbackLogAdmin(admin.ModelAdmin):
    list_display = ("received_at", "provider", "signature_ok", "outcome")
    list_filter = ("provider", "signature_ok")
    readonly_fields = ("provider", "received_at", "signature_ok", "body", "outcome")
