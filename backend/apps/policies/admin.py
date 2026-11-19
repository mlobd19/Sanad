from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from . import services
from .models import Claim, ClaimPhoto, Commission, InsuredAsset, Policy, Quote


@admin.register(InsuredAsset)
class InsuredAssetAdmin(admin.ModelAdmin):
    list_display = ("reference", "kind", "owner", "created_at")
    search_fields = ("reference", "owner__phone")


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "product", "premium", "expires_at")
    list_filter = ("product__insurer",)


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ("id", "asset", "customer", "product", "premium", "status", "starts_on", "ends_on")
    list_filter = ("status", "product__insurer")
    search_fields = ("asset__reference", "customer__phone", "insurer_reference")
    readonly_fields = ("quote", "customer", "asset", "product", "premium", "status", "decided_by", "decided_at")
    actions = ["validate_selected"]

    @admin.action(description="Valider les polices payées sélectionnées")
    def validate_selected(self, request, queryset):
        done = 0
        for policy in queryset.filter(status=Policy.Status.PAID):
            try:
                services.validate_policy(policy, request.user)
                done += 1
            except ValidationError as exc:
                self.message_user(request, f"Police #{policy.pk} : {exc.messages[0]}", messages.ERROR)
        self.message_user(request, f"{done} police(s) validée(s).")


class ClaimPhotoInline(admin.TabularInline):
    model = ClaimPhoto
    extra = 0


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ("id", "policy", "occurred_on", "status", "created_at")
    list_filter = ("status",)
    inlines = [ClaimPhotoInline]


@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    list_display = ("policy", "insurer", "amount", "period", "is_paid")
    list_filter = ("insurer", "period", "is_paid")
