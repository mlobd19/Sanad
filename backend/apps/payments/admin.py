from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.audit.models import record
from apps.backoffice.actions import reason_page
from apps.backoffice.ui import mru, pill, status_pill

from .models import CallbackLog, Payment, Refund


class ReadOnlyAdmin(admin.ModelAdmin):
    """Les mouvements d'argent ne se saisissent jamais à la main."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class RefundInline(admin.TabularInline):
    model = Refund
    extra = 0
    fields = ("policy", "amount", "status", "external_ref", "note", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(ReadOnlyAdmin):
    list_display = ("short_id", "paid_for", "provider", "amount_display", "status_display", "external_ref",
                    "created_at")
    list_filter = ("status", "provider")
    search_fields = ("external_ref", "payer_phone", "policy__asset__reference", "order__company__legal_name")
    date_hierarchy = "created_at"
    inlines = [RefundInline]

    @admin.display(description=_("identifiant"))
    def short_id(self, payment):
        return str(payment.pk)[:8]

    @admin.display(description=_("pour"))
    def paid_for(self, payment):
        if payment.order_id:
            return gettext("Commande n° %(id)s") % {"id": payment.order_id}
        return str(payment.policy)

    @admin.display(description=_("montant"), ordering="amount")
    def amount_display(self, payment):
        return format_html('<span class="sn-mono">{}</span>', mru(payment.amount))

    @admin.display(description=_("statut"), ordering="status")
    def status_display(self, payment):
        return status_pill(payment)


@admin.register(Refund)
class RefundAdmin(ReadOnlyAdmin):
    list_display = ("payment", "policy", "amount_display", "status_display", "external_ref", "note", "created_at")
    list_filter = ("status",)
    search_fields = ("external_ref", "note")
    actions = ["mark_done_manually"]

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("payments.change_refund")  # nécessaire à l'action ci-dessous

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in Refund._meta.fields]

    @admin.display(description=_("montant"), ordering="amount")
    def amount_display(self, refund):
        return format_html('<span class="sn-mono">{}</span>', mru(refund.amount))

    @admin.display(description=_("statut"), ordering="status")
    def status_display(self, refund):
        return status_pill(refund)

    @admin.action(description=_("Marquer comme remboursé à la main…"))
    def mark_done_manually(self, request, queryset):
        def apply(refund, reference):
            refund.status = Refund.Status.DONE
            refund.external_ref = reference[:80]
            refund.note = (refund.note + " · " if refund.note else "") + gettext("remboursé à la main")
            refund.save(update_fields=["status", "external_ref", "note"])
            record("refund.done_manually", refund.payment, actor=request.user, reference=reference)

        return reason_page(
            request, self, objects=list(queryset.filter(status=Refund.Status.FAILED)), action="mark_done_manually",
            title=gettext("Remboursement fait à la main"),
            intro=gettext("À utiliser une fois le remboursement effectué avec l'opérateur."),
            label=gettext("Référence de l'opération chez l'opérateur (obligatoire)"),
            submit=gettext("Marquer comme remboursé"), apply=apply, danger=False,
            done_message=gettext("%(n)s remboursement(s) marqué(s) comme effectué(s)."),
        )


@admin.register(CallbackLog)
class CallbackLogAdmin(ReadOnlyAdmin):
    list_display = ("received_at", "provider", "signature_display", "outcome")
    list_filter = ("provider", "signature_ok")

    @admin.display(description=_("signature valide"), ordering="signature_ok")
    def signature_display(self, log):
        return pill("ok" if log.signature_ok else "bad", gettext("Oui") if log.signature_ok else gettext("Non"))
