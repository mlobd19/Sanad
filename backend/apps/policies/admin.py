from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.backoffice.actions import reason_page
from apps.backoffice.ui import mru, pill, status_pill

from . import services
from .models import Claim, ClaimPhoto, Commission, InsuredAsset, Order, Policy, Quote


class ReadOnlyMixin:
    """Données issues des parcours (paiement, devis…) : consultables, jamais saisies à la main."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ClientTypeFilter(admin.SimpleListFilter):
    title = _("type de client")
    parameter_name = "client"

    def lookups(self, request, model_admin):
        return [("person", _("Particulier")), ("company", _("Entreprise"))]

    def queryset(self, request, queryset):
        if self.value() == "person":
            return queryset.filter(company__isnull=True)
        if self.value() == "company":
            return queryset.filter(company__isnull=False)
        return queryset


@admin.register(Policy)
class PolicyAdmin(ReadOnlyMixin, admin.ModelAdmin):
    list_display = ("id", "plate_display", "client_display", "insurer_display", "premium_display", "status_display",
                    "period_display")
    list_display_links = ("id", "plate_display")
    list_filter = ("status", "product__insurer", ClientTypeFilter)
    search_fields = ("asset__reference", "customer__phone", "customer__full_name", "company__legal_name",
                     "company__nif", "insurer_reference")
    date_hierarchy = "created_at"
    actions = ["validate_selected", "refuse_selected", "cancel_selected"]
    fieldsets = (
        (_("Contrat"), {"fields": ("status_display", "product", "premium_display", "starts_on", "ends_on",
                                   "insurer_reference")}),
        (_("Client"), {"fields": ("customer", "company", "asset", "order")}),
        (_("Décision de l'assureur"), {"fields": ("decided_by", "decided_at", "refusal_reason")}),
        (_("Historique"), {"fields": ("quote", "renewal_of", "created_at", "updated_at"), "classes": ("collapse",)}),
    )
    readonly_fields = ("status_display", "product", "premium_display", "starts_on", "ends_on", "insurer_reference",
                       "customer", "company", "asset", "order", "decided_by", "decided_at", "refusal_reason", "quote",
                       "renewal_of", "created_at", "updated_at")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("asset", "customer", "company", "product__insurer")

    @admin.display(description=_("immatriculation"), ordering="asset__reference")
    def plate_display(self, policy):
        return policy.asset.reference

    @admin.display(description=_("client"))
    def client_display(self, policy):
        if policy.company_id:
            return format_html('{}<span class="sn-sub">{} · <span class="sn-mono">{}</span></span>',
                               policy.company.legal_name, gettext("Entreprise"), policy.company.nif)
        return format_html('{}<span class="sn-sub sn-mono">{}</span>', policy.customer.full_name or "—",
                           policy.customer.phone)

    @admin.display(description=_("assureur et formule"), ordering="product__insurer__name")
    def insurer_display(self, policy):
        return format_html("{}<span class=\"sn-sub\">{}</span>", policy.product.insurer.name, policy.product.name)

    @admin.display(description=_("prime"), ordering="premium")
    def premium_display(self, policy):
        return format_html('<span class="sn-mono">{}</span>', mru(policy.premium))

    @admin.display(description=_("statut"), ordering="status")
    def status_display(self, policy):
        return status_pill(policy)

    @admin.display(description=_("période"), ordering="starts_on")
    def period_display(self, policy):
        # Format neutre, lisible en français comme en arabe (le format court arabe se brouille ici).
        return format_html('<span class="sn-mono">{} → {}</span>', policy.starts_on.strftime("%d/%m/%Y"),
                           policy.ends_on.strftime("%d/%m/%Y"))

    @admin.action(description=_("Valider les polices payées (à la place de l'assureur)"))
    def validate_selected(self, request, queryset):
        done = 0
        for policy in queryset.filter(status=Policy.Status.PAID):
            try:
                services.validate_policy(policy, request.user)
                done += 1
            except ValidationError as exc:
                self.message_user(request, f"{policy} : {exc.messages[0]}", messages.ERROR)
        self.message_user(request, gettext("%(n)s police(s) validée(s).") % {"n": done},
                          messages.SUCCESS if done else messages.WARNING)

    @admin.action(description=_("Refuser les polices payées et rembourser…"))
    def refuse_selected(self, request, queryset):
        return reason_page(
            request, self, objects=list(queryset.filter(status=Policy.Status.PAID)), action="refuse_selected",
            title=gettext("Refuser des polices"),
            intro=gettext("Le client est remboursé automatiquement et voit ce motif dans son application."),
            label=gettext("Motif du refus (obligatoire)"), submit=gettext("Refuser et rembourser"),
            apply=lambda p, reason: services.refuse_policy(p, request.user, reason),
            done_message=gettext("%(n)s police(s) refusée(s) et remboursée(s)."),
        )

    @admin.action(description=_("Résilier les polices actives…"))
    def cancel_selected(self, request, queryset):
        return reason_page(
            request, self, objects=list(queryset.filter(status=Policy.Status.ACTIVE)), action="cancel_selected",
            title=gettext("Résilier des polices"),
            intro=gettext("L'attestation est révoquée : le QR code affichera « révoquée » lors d'un contrôle."),
            label=gettext("Motif de la résiliation (obligatoire)"), submit=gettext("Résilier"),
            apply=lambda p, reason: services.cancel_policy(p, request.user, reason),
            done_message=gettext("%(n)s police(s) résiliée(s)."),
        )


class OrderPolicyInline(admin.TabularInline):
    model = Policy
    fk_name = "order"
    extra = 0
    can_delete = False
    fields = ("asset", "product", "premium", "status")
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(ReadOnlyMixin, admin.ModelAdmin):
    list_display = ("id", "company", "created_by", "total_display", "policies_count", "created_at")
    search_fields = ("company__legal_name", "company__nif")
    readonly_fields = ("company", "created_by", "created_at")
    inlines = [OrderPolicyInline]

    @admin.display(description=_("total"))
    def total_display(self, order):
        return format_html('<span class="sn-mono">{}</span>', mru(order.total))

    @admin.display(description=_("polices"))
    def policies_count(self, order):
        return order.policies.count()


@admin.register(InsuredAsset)
class InsuredAssetAdmin(ReadOnlyMixin, admin.ModelAdmin):
    list_display = ("reference", "kind", "owner", "company", "created_at")
    list_filter = ("kind",)
    search_fields = ("reference", "owner__phone", "company__legal_name")
    readonly_fields = ("owner", "company", "kind", "reference", "attributes", "created_at")


@admin.register(Quote)
class QuoteAdmin(ReadOnlyMixin, admin.ModelAdmin):
    list_display = ("id", "customer", "asset", "product", "premium_display", "expires_at")
    list_filter = ("product__insurer",)
    readonly_fields = ("customer", "asset", "product", "premium", "tariff_version", "attributes_snapshot",
                       "created_at", "expires_at")

    @admin.display(description=_("prime"), ordering="premium")
    def premium_display(self, quote):
        return mru(quote.premium)


class ClaimPhotoInline(admin.TabularInline):
    model = ClaimPhoto
    extra = 0
    can_delete = False
    fields = ("open_file", "uploaded_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description=_("photo"))
    def open_file(self, photo):
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', photo.file.url, gettext("Ouvrir"))


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ("id", "policy", "occurred_on", "status_display", "created_at")
    list_filter = ("status",)
    search_fields = ("policy__asset__reference", "description")
    fields = ("policy", "occurred_on", "description", "status", "created_at")
    readonly_fields = ("policy", "occurred_on", "description", "created_at")
    inlines = [ClaimPhotoInline]

    def has_add_permission(self, request):
        return False

    @admin.display(description=_("statut"), ordering="status")
    def status_display(self, claim):
        return status_pill(claim)


@admin.register(Commission)
class CommissionAdmin(ReadOnlyMixin, admin.ModelAdmin):
    list_display = ("policy", "insurer", "rate_display", "amount_display", "period", "paid_display")
    list_filter = ("insurer", "period", "is_paid")
    readonly_fields = ("policy", "insurer", "rate", "amount", "period", "is_paid", "created_at")
    actions = ["mark_paid"]

    @admin.display(description=_("taux"), ordering="rate")
    def rate_display(self, c):
        return f"{c.rate * 100:.2f}".rstrip("0").rstrip(".") + " %"

    @admin.display(description=_("montant"), ordering="amount")
    def amount_display(self, c):
        return format_html('<span class="sn-mono">{}</span>', mru(c.amount))

    @admin.display(description=_("payée"), ordering="is_paid")
    def paid_display(self, c):
        return pill("ok" if c.is_paid else "warn", gettext("Payée") if c.is_paid else gettext("À payer"),
                    "ok" if c.is_paid else "warn")

    @admin.action(description=_("Marquer comme payées"))
    def mark_paid(self, request, queryset):
        n = queryset.filter(is_paid=False).update(is_paid=True)
        self.message_user(request, gettext("%(n)s commission(s) marquée(s) comme payée(s).") % {"n": n},
                          messages.SUCCESS)
