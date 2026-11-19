from django.contrib import admin
from django.utils.html import format_html

from .models import Insurer, Product, TariffFactor


class TariffFactorInline(admin.TabularInline):
    model = TariffFactor
    extra = 0


def logo_preview(insurer, height=40):
    if not insurer.logo:
        return "—"
    return format_html('<img src="{}" alt="" style="height:{}px;max-width:160px;object-fit:contain">', insurer.logo.url, height)


@admin.register(Insurer)
class InsurerAdmin(admin.ModelAdmin):
    list_display = ("name", "logo_thumb", "legal_name", "integration", "commission_rate", "auto_validate", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("logo_large",)
    fields = ("name", "legal_name", "slug", "logo", "logo_large", "contact_email", "integration",
              "commission_rate", "auto_validate", "is_active")

    @admin.display(description="Logo")
    def logo_thumb(self, obj):
        return logo_preview(obj, 28)

    @admin.display(description="Aperçu")
    def logo_large(self, obj):
        return logo_preview(obj, 80)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "insurer", "branch", "base_premium", "tariff_version", "is_indicative", "is_active")
    list_filter = ("insurer", "branch", "is_indicative", "is_active")
    inlines = [TariffFactorInline]
