from django.contrib import admin

from .models import Insurer, Product, TariffFactor


class TariffFactorInline(admin.TabularInline):
    model = TariffFactor
    extra = 0


@admin.register(Insurer)
class InsurerAdmin(admin.ModelAdmin):
    list_display = ("name", "legal_name", "integration", "commission_rate", "auto_validate", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "insurer", "branch", "base_premium", "tariff_version", "is_indicative", "is_active")
    list_filter = ("insurer", "branch", "is_indicative", "is_active")
    inlines = [TariffFactorInline]
